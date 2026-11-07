"""
Reads the processed transactions and keeps only
the days inside the train / val / test periods. Every rule sees only its own period.
Time order between hops is not enforced, so windows look both ways.

Writes two Parquet tables, partitioned by period:
    features_abd/  period, acct, n_out, d_out, usd_out, n_in, d_in, usd_in,
                   fan_ratio, flow_match, chain_score
    edges/         period, src, dst, usd   (USD summed per sender-receiver pair)

Glue arguments:
    --transactions_path  s3://.../processed/transactions/ for one dataset, with one
                         transaction_date=YYYY-MM-DD/ folder per day (schema as
                         sample_data/processed-transactions.parquet). Only the period
                         days' folders are read.
    --periods            train=2022-09-01:2022-09-08,val=2022-09-11:2022-09-12,test=2022-09-15:2022-09-16
    --output_path        s3://.../features/q1/
"""
import itertools
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, Window

EPS = 1e-6
WINDOW_SECONDS = 72 * 3600
BLOCK_DAYS = 3
USD = "US Dollar"

log = logging.getLogger("rule_features")


@dataclass(frozen=True)
class Period:
    name: str
    start: date
    end: date


def parse_periods(spec: str) -> list[Period]:
    periods = []
    for part in spec.split(","):
        name, dates = part.split("=")
        start, end = dates.split(":")
        periods.append(Period(name.strip(), date.fromisoformat(start.strip()), date.fromisoformat(end.strip())))
    for p in periods:
        if p.start > p.end:
            raise ValueError(f"period {p.name} starts after it ends")
    for earlier, later in itertools.pairwise(periods):
        if later.start <= earlier.end:
            raise ValueError(f"period {later.name} must start after {earlier.name} ends")
    return periods


def period_days(periods: list[Period]) -> list[date]:
    return [p.start + timedelta(days=d) for p in periods for d in range((p.end - p.start).days + 1)]


def usd_rates(raw: DataFrame, period: Period) -> DataFrame:
    """Units of each currency per 1 USD, from conversions with USD on exactly one side, inside `period` only.

    Pass the train period, so later periods never shape train amounts.
    """
    pay_usd = F.col("payment_currency") == USD
    recv_usd = F.col("receiving_currency") == USD
    usd_amount = F.when(pay_usd, F.col("amount_paid")).otherwise(F.col("amount_received")).cast("double")
    other_amount = F.when(pay_usd, F.col("amount_received")).otherwise(F.col("amount_paid")).cast("double")
    converted = (
        raw.where(F.to_date("txn_ts").between(F.lit(period.start), F.lit(period.end)))
        .where((pay_usd != recv_usd) & (usd_amount > 100))
        .groupBy(F.when(pay_usd, F.col("receiving_currency")).otherwise(F.col("payment_currency")).alias("currency"))
        .agg(F.percentile_approx(other_amount / usd_amount, 0.5).alias("per_usd"))
    )
    usd = raw.sparkSession.createDataFrame([(USD, 1.0)], "currency string, per_usd double")
    return converted.unionByName(usd)


def prepare(raw: DataFrame, periods: list[Period], rates: DataFrame) -> DataFrame:
    """Processed transactions in, one row per usable transaction out: period, period_start, ts, src, dst, usd.

    Drops gap days, self-transfers, and rows whose currencies have no rate.
    """
    period_table = raw.sparkSession.createDataFrame(
        [(p.name, p.start, p.end) for p in periods], "period string, period_start date, period_end date"
    )
    pay = rates.select(F.col("currency").alias("payment_currency"), F.col("per_usd").alias("pay_per_usd"))
    recv = rates.select(F.col("currency").alias("receiving_currency"), F.col("per_usd").alias("recv_per_usd"))
    paid = F.col("amount_paid").cast("double") / F.col("pay_per_usd")
    received = F.col("amount_received").cast("double") / F.col("recv_per_usd")
    return (
        raw.join(F.broadcast(period_table), F.to_date("txn_ts").between(F.col("period_start"), F.col("period_end")))
        .join(F.broadcast(pay), "payment_currency", "left")
        .join(F.broadcast(recv), "receiving_currency", "left")
        .select(
            "period",
            "period_start",
            F.col("txn_ts").alias("ts"),
            F.concat_ws("|", "from_bank", "from_account").alias("src"),
            F.concat_ws("|", "to_bank", "to_account").alias("dst"),
            F.coalesce(paid, received).alias("usd"),
        )
        .where((F.col("src") != F.col("dst")) & (F.col("usd") > 0))
    )


def account_flows(txns: DataFrame) -> DataFrame:
    """Each transaction twice: once as the sender's outflow, once as the receiver's inflow."""
    out = txns.select("period", "period_start", "ts", F.col("src").alias("acct"), "usd", F.lit(True).alias("is_out"))
    inn = txns.select("period", "period_start", "ts", F.col("dst").alias("acct"), "usd", F.lit(False).alias("is_out"))
    return out.unionByName(inn)


def rule_a(txns: DataFrame) -> DataFrame:
    """Fan ratio from distinct counterparties, plus activity counts and volumes."""
    out = txns.groupBy("period", F.col("src").alias("acct")).agg(
        F.count("*").alias("n_out"), F.countDistinct("dst").alias("d_out"), F.sum("usd").alias("usd_out")
    )
    inn = txns.groupBy("period", F.col("dst").alias("acct")).agg(
        F.count("*").alias("n_in"), F.countDistinct("src").alias("d_in"), F.sum("usd").alias("usd_in")
    )
    return (
        out.join(inn, ["period", "acct"], "full")
        .fillna(0)
        .withColumn("fan_ratio", F.least("d_in", "d_out") / (F.greatest("d_in", "d_out") + EPS))
    )


def rule_b(txns: DataFrame) -> DataFrame:
    """Best in/out volume balance over any window of +-72 h around one of the account's transactions."""
    window = (
        Window.partitionBy("period", "acct")
        .orderBy(F.col("ts").cast("long"))
        .rangeBetween(-WINDOW_SECONDS, WINDOW_SECONDS)
    )
    v_in = F.sum(F.when(~F.col("is_out"), F.col("usd")).otherwise(0.0)).over(window)
    v_out = F.sum(F.when(F.col("is_out"), F.col("usd")).otherwise(0.0)).over(window)
    flow = 100 * F.least(v_in, v_out) / (F.greatest(v_in, v_out) + EPS)
    return (
        account_flows(txns)
        .select("period", "acct", flow.alias("flow"))
        .groupBy("period", "acct")
        .agg(F.max("flow").alias("flow_match"))
    )


def rule_d(txns: DataFrame) -> DataFrame:
    """Best amount match between one inflow and one outflow in the same 3-day block of the period.

    Sorting a block's flows by amount puts each outflow next to its closest inflows, so the
    best pair is found without building every in x out pair (which explodes at hub accounts).
    """
    by_amount = Window.partitionBy("period", "acct", "block").orderBy("usd", "is_out")
    inflow = F.when(~F.col("is_out"), F.col("usd"))
    below = F.last(inflow, ignorenulls=True).over(by_amount.rowsBetween(Window.unboundedPreceding, Window.currentRow))
    above = F.first(inflow, ignorenulls=True).over(by_amount.rowsBetween(Window.currentRow, Window.unboundedFollowing))
    pair = 100 * F.greatest(below / F.col("usd"), F.col("usd") / above)
    return (
        account_flows(txns)
        .withColumn("block", F.floor(F.datediff(F.to_date("ts"), F.col("period_start")) / BLOCK_DAYS))
        .select("period", "acct", "is_out", pair.alias("pair"))
        .where(F.col("is_out"))
        .groupBy("period", "acct")
        .agg(F.max("pair").alias("chain_score"))
    )


def features_abd(txns: DataFrame) -> DataFrame:
    return (
        rule_a(txns)
        .join(rule_b(txns), ["period", "acct"], "left")
        .join(rule_d(txns), ["period", "acct"], "left")
        .fillna(0.0, subset=["flow_match", "chain_score"])
    )


def edges(txns: DataFrame) -> DataFrame:
    return txns.groupBy("period", "src", "dst").agg(F.sum("usd").alias("usd"))


def unpriced_currencies(raw: DataFrame, rates: DataFrame) -> list[str]:
    seen = raw.select(F.col("payment_currency").alias("currency")).union(raw.select("receiving_currency")).distinct()
    return sorted(r["currency"] for r in seen.join(rates, "currency", "left_anti").collect())


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
    # imported here to keep the rules testable locally.
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "transactions_path", "periods", "output_path"])
    log.info("arguments: %s", {k: args[k] for k in ("transactions_path", "periods", "output_path")})
    periods = parse_periods(args["periods"])
    glue_context = GlueContext(SparkContext.getOrCreate())
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    raw = spark.read.parquet(args["transactions_path"]).where(
        F.col("transaction_date").cast("date").isin(period_days(periods))
    )
    with stage("USD rates"):
        rates = usd_rates(raw, periods[0]).cache()
        log.info("USD rates from %s: %s", periods[0].name, {r["currency"]: r["per_usd"] for r in rates.collect()})
        missing = unpriced_currencies(raw, rates)
        if missing:
            log.warning("no USD rate for %s, so their transactions are dropped", missing)

    with stage("prepare transactions"):
        txns = prepare(raw, periods, rates).cache()
        kept = rows_per_period(txns)
        log.info("transactions kept per period: %s", kept)
        empty = [p.name for p in periods if kept.get(p.name, 0) == 0]
        if empty:
            raise ValueError(f"no transactions in period(s) {empty}; check --transactions_path and --periods")

    output = args["output_path"].rstrip("/")
    for name, table in (("features_abd", features_abd(txns)), ("edges", edges(txns))):
        path = f"{output}/{name}/"
        with stage(f"write {name}"):
            table.write.mode("overwrite").partitionBy("period").parquet(path)
        log.info("%s rows per period, read back from %s: %s", name, path, rows_per_period(spark.read.parquet(path)))
    job.commit()


if __name__ == "__main__":
    main()
