import sys, csv, io, re, collections
import boto3
from awsglue.utils import getResolvedOptions

args = getResolvedOptions(sys.argv, ["BUCKET", "INPUT_KEY", "OUTPUT_KEY"])
s3 = boto3.client("s3")
text = s3.get_object(Bucket=args["BUCKET"], Key=args["INPUT_KEY"])["Body"].read().decode("utf-8")

out = io.StringIO()
w = csv.writer(out, lineterminator="\n")
attempt, ptype, detail = 0, None, None
lines_ok, lines_bad, types = 0, 0, collections.Counter()

for line in text.splitlines():
    line = line.strip()
    if not line:
        continue
    if line.startswith("BEGIN LAUNDERING ATTEMPT"):
        attempt += 1
        m = re.match(r"BEGIN LAUNDERING ATTEMPT\s*-\s*([A-Z\-]+)\s*:?\s*(.*)", line)
        ptype, detail = (m.group(1), m.group(2)) if m else ("UNKNOWN", line)
        types[ptype] += 1
        continue
    if line.startswith("END LAUNDERING ATTEMPT"):
        ptype = None
        continue
    fields = next(csv.reader([line]))
    if ptype is None or len(fields) != 11:
        lines_bad += 1
        continue
    w.writerow([attempt, ptype, detail] + fields)
    lines_ok += 1

s3.put_object(Bucket=args["BUCKET"], Key=args["OUTPUT_KEY"], Body=out.getvalue().encode("utf-8"))
print({"attempts": attempt, "lines_written": lines_ok, "lines_skipped": lines_bad, "attempts_by_type": dict(types)})
