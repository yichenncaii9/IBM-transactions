"""
Reads job 1's features_abd/ and edges/. An account is a seed in a period when any of
its Rule A, B or D scores beats the cutoff learned from the train period. Seeds start
at taint 1.0. Each round, every account's taint becomes the USD-weighted share of its
inflow that came from tainted senders. A fixed number of rounds stops cycles looping.

Writes features/ (features_abd columns + taint), partitioned by period.

Glue arguments:
    --input_path    s3://.../features/q1/   (job 1's output_path)
    --hit_quantile  0.99                    (top 1% of train accounts per rule are hits)
    --rounds        3
"""
import functools
import logging
import operator
import sys
import time
from contextlib import contextmanager

import pyspark.sql.functions as F
from pyspark.sql import DataFrame

EPS = 1e-6
RULE_COLUMNS = ("fan_ratio", "flow_match", "chain_score")
TRAIN = "train"

log = logging.getLogger("rule_taint")


def hit_cutoffs(features: DataFrame, quantile: float) -> dict[str, float]:
    train = features.where(F.col("period") == TRAIN)
    row = train.agg(*[F.percentile_approx(c, quantile).alias(c) for c in RULE_COLUMNS]).first()
    return {c: row[c] for c in RULE_COLUMNS}


def seeds(features: DataFrame, cutoffs: dict[str, float]) -> DataFrame:
    """Strictly above the cutoff, so a cutoff of 0 does not seed every account."""
    hit = functools.reduce(operator.or_, [F.col(c) > cutoff for c, cutoff in cutoffs.items()])
    return features.where(hit).select("period", "acct")


def train_hits_per_rule(features: DataFrame, cutoffs: dict[str, float]) -> dict[str, int]:
    train = features.where(F.col("period") == TRAIN)
    row = train.agg(*[F.count(F.when(F.col(c) > cutoff, 1)).alias(c) for c, cutoff in cutoffs.items()]).first()
    return {c: row[c] for c in cutoffs}


def taint(edges: DataFrame, seed: DataFrame, rounds: int) -> DataFrame:
    """period, acct, taint for every seed and every account reached within `rounds` hops."""
    inflow = edges.groupBy("period", "dst").agg(F.sum("usd").alias("usd_in"))
    fixed = seed.select("period", "acct", F.lit(1.0).alias("taint"))
    current = fixed
    for _ in range(rounds):
        spread = (
            edges.join(current.withColumnRenamed("acct", "src"), ["period", "src"])
            .groupBy("period", "dst")
            .agg(F.sum(F.col("usd") * F.col("taint")).alias("tainted_usd"))
            .join(inflow, ["period", "dst"])
            .select("period", F.col("dst").alias("acct"), (F.col("tainted_usd") / (F.col("usd_in") + EPS)).alias("taint"))
        )
        current = spread.unionByName(fixed).groupBy("period", "acct").agg(F.max("taint").alias("taint"))
    return current


def with_taint(features: DataFrame, taint_scores: DataFrame) -> DataFrame:
    return features.join(taint_scores, ["period", "acct"], "left").fillna(0.0, subset=["taint"])


def rows_per_period(df: DataFrame) -> dict[str, int]:
    return {r["period"]: r["count"] for r in df.groupBy("period").count().collect()}


@contextmanager
def stage(name: str):
    """Logs when a step starts and how long it took; a failing step leaves only its 'started' line."""
    start = time.monotonic()
    log.info("%s: started", name)
    yield
    log.info("%s: done in %.1f min", name, (time.monotonic() - start) / 60)


def main() -> None:
    # awsglue only exists on Glue, so it is imported here to keep the rules testable locally.
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "input_path", "hit_quantile", "rounds"])
    log.info("arguments: %s", {k: args[k] for k in ("input_path", "hit_quantile", "rounds")})
    glue_context = GlueContext(SparkContext.getOrCreate())
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    spark = glue_context.spark_session
    root = args["input_path"].rstrip("/")
    features = spark.read.parquet(f"{root}/features_abd/").cache()
    edge_list = spark.read.parquet(f"{root}/edges/").cache()
    rows = rows_per_period(features)
    log.info("features_abd rows per period: %s", rows)
    if rows.get(TRAIN, 0) == 0:
        raise ValueError(f"no {TRAIN} rows in {root}/features_abd/; did job 1 finish, and is --input_path right?")

    with stage("seeds"):
        cutoffs = hit_cutoffs(features, float(args["hit_quantile"]))
        log.info("hit cutoffs from %s at quantile %s: %s", TRAIN, args["hit_quantile"], cutoffs)
        hits = train_hits_per_rule(features, cutoffs)
        log.info("%s accounts above each cutoff: %s", TRAIN, hits)
        for rule in [r for r, n in hits.items() if n == 0]:
            log.warning("%s seeds nobody: no %s account is strictly above its cutoff (ties at the top?)", rule, TRAIN)
        seed = seeds(features, cutoffs).cache()
        log.info("seeds per period: %s", rows_per_period(seed))

    path = f"{root}/features/"
    with stage("taint and write features"):
        scores = taint(edge_list, seed, int(args["rounds"]))
        with_taint(features, scores).write.mode("overwrite").partitionBy("period").parquet(path)
    written = spark.read.parquet(path)
    log.info("features rows per period, read back from %s: %s", path, rows_per_period(written))
    log.info("accounts with taint > 0 per period: %s", rows_per_period(written.where(F.col("taint") > 0)))
    job.commit()


if __name__ == "__main__":
    main()
