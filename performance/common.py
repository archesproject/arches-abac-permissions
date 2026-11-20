"""Names shared by the seed and run commands."""

import hashlib
import os
import uuid

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

GRAPH_A_SLUG = "abac_perf_a"
GRAPH_B_SLUG = "abac_perf_b"
LIFECYCLE_NAME = "ABAC perf lifecycle"
STATE_NAMES = ("Draft", "Active", "Retired")  # 70% / 20% / 10% of graph A
# Size presets: graph A resources, graph B resources, HIGH_MOD (every Nth
# resource holds the "high" value), resource-set sizes.
SIZES = {
    "1k": (1_000, 200, 250, (10, 100, 500)),
    "50k": (50_000, 10_000, 1_000, (500, 5_000, 25_000)),
    "100k": (100_000, 20_000, 2_500, (1_000, 10_000, 50_000)),
    "1m": (1_000_000, 200_000, 10_000, (100, 10_000, 500_000)),
}
SIZE = os.environ.get("ABAC_PERF_SIZE", "1k")
RESOURCES, RESOURCES_B, HIGH_MOD, SET_SIZES = SIZES[SIZE]


def database_name(size):
    return "abac_perf" if size == "1m" else f"abac_perf_{size}"


def assert_safe(size):
    """Refuse to run outside DEBUG or against a non-perf database."""
    name = connection.settings_dict["NAME"]
    if not settings.DEBUG or not name.startswith("abac_perf"):
        raise CommandError(
            f"Refusing to run (DEBUG={settings.DEBUG}, database={name})."
        )
    if size != SIZE:
        raise CommandError(f"--size {size} must match ABAC_PERF_SIZE={SIZE}.")


COUNT_TABLES = (
    "resource_instances",
    "tiles",
    "geojson_geometries",
    "resource_set_member",
)

# Node aliases of graph A (one nodegroup each, except the three booleans).
STRING, NUMBER, DOMAIN, RESOURCE, GEOMETRY = "str", "num", "dvl", "ri", "geo"
BOOLEANS = ("bool_high", "bool_mid", "bool_low")

# Value buckets: share of graph A resources holding the value.
BUCKETS = ("high", "mid", "low")  # ~0.01%, ~1%, ~50%
STRING_VALUES = {
    "high": "rare-value",
    "mid": "medium-value",
    "low": "common-value",
}
NUMBER_VALUES = {"high": "1", "mid": "2", "low": "3"}

# Geometries cover lon/lat 0..10; an area's share of points ~ its share of this box.
REGION = 10.0


def resource_id_sql(prefix, index="i"):
    """Deterministic resource id for the i-th resource of a graph."""
    return f"md5('{prefix}' || {index})::uuid"


def get_graph(slug):
    from arches.app.models.models import GraphModel

    return GraphModel.objects.get(slug=slug)


def get_nodes(slug):
    from arches.app.models.models import Node

    return {node.alias: node for node in Node.objects.filter(graph__slug=slug)}


def hash_uuid(text):
    return uuid.UUID(hashlib.md5(text.encode()).hexdigest())


def resource_target(bucket):
    """Graph A resource referenced by the resource-instance node per bucket."""
    index = BUCKETS.index(bucket) + 1
    return hash_uuid(f"A{5000 + index if RESOURCES > 5000 + index else index}")


def domain_option(index):
    return hash_uuid(f"option{index}")
