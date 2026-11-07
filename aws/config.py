"""Shared AWS names for the group account. Override any of them with env vars."""
import os

REGION = os.environ.get('AWS_REGION', 'us-east-1')
BUCKET = os.environ.get('AML_BUCKET', 'is459-g2t8-aml-897729121624')
WORKGROUP = os.environ.get('ATHENA_WORKGROUP', 'is459')
DATABASE = os.environ.get('GLUE_DATABASE', 'is459_aml')
ATHENA_OUTPUT = os.environ.get('ATHENA_OUTPUT', f's3://{BUCKET}/athena-results/')
# Team account (897729121624) is a full AWS account, not a Learner Lab: no LabRole.
GLUE_ROLE = os.environ.get('GLUE_ROLE', 'is459-aml-glue-role')

# Raw files already in the bucket (uploaded 30 Oct), cleaned by Glue job is459-clean-transaction
RAW_FILES = ['raw/hi-medium/HI-Medium_Trans.csv', 'raw/hi-medium/HI-Medium_accounts.csv',
             'raw/hi-medium/HI-Medium_Patterns.txt']


def athena(sql, wait=True):
    """Run one Athena statement; return rows as lists of strings (header first)."""
    import time
    import boto3
    a = boto3.client('athena', region_name=REGION)
    qid = a.start_query_execution(
        QueryString=sql, WorkGroup=WORKGROUP,
        ResultConfiguration={'OutputLocation': ATHENA_OUTPUT})['QueryExecutionId']
    if not wait:
        return qid
    while True:
        st = a.get_query_execution(QueryExecutionId=qid)['QueryExecution']['Status']
        if st['State'] in ('SUCCEEDED', 'FAILED', 'CANCELLED'):
            break
        time.sleep(1.5)
    if st['State'] != 'SUCCEEDED':
        raise RuntimeError(f"Athena {st['State']}: {st.get('StateChangeReason')}\n{sql}")
    rows = a.get_query_results(QueryExecutionId=qid)['ResultSet']['Rows']
    return [[c.get('VarCharValue', '') for c in r['Data']] for r in rows]
