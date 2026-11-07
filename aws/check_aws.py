"""Step A1: prove the AWS keys work and one Athena query runs.

    python aws/check_aws.py

Prints who you are, what is in the bucket, and runs SELECT 1 in Athena.
Post "AWS works" in the group chat once all three pass.
"""
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

import config as C


def main():
    try:
        ident = boto3.client('sts', region_name=C.REGION).get_caller_identity()
    except (BotoCoreError, ClientError) as e:
        sys.exit(f'FAIL credentials: {e}\nRun: .venv/bin/aws configure  (team IAM user keys, region us-east-1)'
                 f', then rerun.')
    print(f"OK   credentials: account {ident['Account']}, {ident['Arn'].split('/')[-2:]}")

    s3 = boto3.client('s3', region_name=C.REGION)
    try:
        resp = s3.list_objects_v2(Bucket=C.BUCKET, Delimiter='/')
        tops = [p['Prefix'] for p in resp.get('CommonPrefixes', [])]
        print(f'OK   bucket s3://{C.BUCKET}/ top folders: {tops or "(empty)"}')
        for key in C.RAW_FILES:
            try:
                h = s3.head_object(Bucket=C.BUCKET, Key=key)
                print(f"       {key}: {h['ContentLength'] / 1e6:,.0f} MB")
            except ClientError:
                print(f'       {key}: missing')
    except ClientError as e:
        sys.exit(f'FAIL bucket {C.BUCKET}: {e}\nWrong account, or set AML_BUCKET.')

    # Read-only: which of the planned resources exist (creating them needs Xinqi's OK).
    missing = []
    for label, call in [
        (f'Glue role {C.GLUE_ROLE}', lambda: boto3.client('iam').get_role(RoleName=C.GLUE_ROLE)),
        (f'Glue database {C.DATABASE}',
         lambda: boto3.client('glue', region_name=C.REGION).get_database(Name=C.DATABASE)),
        (f'Athena workgroup {C.WORKGROUP}',
         lambda: boto3.client('athena', region_name=C.REGION).get_work_group(WorkGroup=C.WORKGROUP)),
    ]:
        try:
            call()
            print(f'OK   {label}')
        except ClientError as e:
            print(f'MISS {label}: {e.response["Error"]["Code"]}')
            missing.append(label)
    if missing:
        sys.exit('\nMissing resources above: get Xinqi to approve creating them, then rerun.')

    try:
        rows = C.athena('SELECT 1 AS ok')
        print(f'OK   Athena workgroup {C.WORKGROUP}: SELECT 1 -> {rows[1][0]}')
        dbs = [r[0] for r in C.athena('SHOW DATABASES')[0:]]
        print(f'       databases: {dbs}')
    except Exception as e:  # noqa: BLE001
        sys.exit(f'FAIL Athena: {e}')
    print('\nAll checks passed. Post "AWS works" in the group chat.')


if __name__ == '__main__':
    main()
