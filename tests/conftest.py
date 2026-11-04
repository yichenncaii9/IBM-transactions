import os
import sys

import pytest


@pytest.fixture(scope="session")
def spark():
    sql = pytest.importorskip("pyspark.sql")
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    session = (
        sql.SparkSession.builder.master("local[1]")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield session
    session.stop()
