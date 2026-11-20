import os

from tests.test_settings import *

from performance.common import SIZES, database_name

DEBUG = True  # the harness refuses to run otherwise

DATABASES["default"].update(
    NAME=database_name(os.environ.get("ABAC_PERF_SIZE", "1k")),
    HOST=os.environ.get("ABAC_PERF_DB_HOST", "localhost"),
    PORT=os.environ.get("ABAC_PERF_DB_PORT", "5418"),
    USER=os.environ.get("ABAC_PERF_DB_USER", "postgres"),
    PASSWORD=os.environ.get("ABAC_PERF_DB_PASSWORD", ""),
)

INSTALLED_APPS = INSTALLED_APPS + ("performance",)
