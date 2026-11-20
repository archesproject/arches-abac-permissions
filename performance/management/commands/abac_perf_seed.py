import time

import psycopg

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from arches.app.models.models import (
    GraphModel,
    Language,
    Node,
    NodeGroup,
    ResourceInstanceLifecycle,
    ResourceInstanceLifecycleState,
)
from performance import common as c

TRIGGERS = (
    "__arches_check_excess_tiles_trigger",
    "__arches_trg_update_spatial_attributes",
)

# i-th resource's value bucket, shared by every datatype (see perf/common.py).
BUCKET = (
    f"CASE WHEN i % {c.HIGH_MOD} = 0 THEN 'high' WHEN i % 100 = 2 THEN 'mid'"
    " WHEN i % 2 = 1 THEN 'low' ELSE 'other' END"
)


def frac(salt):
    """Deterministic pseudo-random number in [0, 1) per row index i."""
    return (
        f"(('x' || substr(md5(i::text || '{salt}'), 1, 8))::bit(32)::int8"
        f" / 4294967296.0)"
    )


def feature(prefix, point_salt):
    x, y = (
        f"({c.REGION} * {frac(point_salt + 'x')})",
        f"({c.REGION} * {frac(point_salt + 'y')})",
    )
    d = "0.01"
    polygon = (
        f"jsonb_build_array(jsonb_build_array({x}-{d},{y}-{d}),"
        f"jsonb_build_array({x}+{d},{y}-{d}),jsonb_build_array({x}+{d},{y}+{d}),"
        f"jsonb_build_array({x}-{d},{y}+{d}),jsonb_build_array({x}-{d},{y}-{d}))"
    )
    geometry = (
        f"CASE WHEN i % 10 = 3 THEN jsonb_build_object('type','Polygon',"
        f"'coordinates', jsonb_build_array({polygon}))"
        f" ELSE jsonb_build_object('type','Point','coordinates',"
        f"jsonb_build_array({x},{y})) END"
    )
    return (
        f"jsonb_build_object('type','Feature','id',md5('{prefix}' || i || '{point_salt}'),"
        f"'properties',jsonb_build_object(),'geometry',{geometry})"
    )


def geometry_tiledata(prefix, node_id):
    second = (
        "CASE WHEN i % 20 = 7 THEN jsonb_build_array("
        + feature(prefix, "b").replace("i % 10 = 3", "false")
        + ") ELSE '[]'::jsonb END"
    )
    return (
        f"jsonb_build_object('{node_id}', jsonb_build_object('type',"
        f"'FeatureCollection','features', jsonb_build_array({feature(prefix, 'a')})"
        f" || {second}))"
    )


class Command(BaseCommand):
    help = "Seed the abac_perf database with a synthetic dataset."

    def add_arguments(self, parser):
        parser.add_argument("--size", choices=c.SIZES, default="1k")
        parser.add_argument(
            "--recreate", action="store_true", help="drop and rebuild the database"
        )

    def handle(self, *args, **options):
        c.assert_safe(options["size"])
        self.prepare_database(options["recreate"])
        call_command("migrate", verbosity=0)
        if GraphModel.objects.filter(slug=c.GRAPH_A_SLUG).exists():
            raise CommandError("Already seeded; pass --recreate to rebuild.")
        self.started = time.time()
        graphs = self.create_model()
        with connection.cursor() as cursor:
            self.cursor = cursor
            self.seed_resources(c.RESOURCES, c.RESOURCES_B, graphs)
            self.seed_sets(c.RESOURCES)
            self.log("VACUUM ANALYZE")
            cursor.execute("VACUUM ANALYZE")
            self.report(cursor)
        self.log("done")

    @staticmethod
    def prepare_database(recreate):
        """Create the database from template_postgis if missing (optionally recreating)."""
        db = connection.settings_dict
        name = db["NAME"]  # abac_perf*, checked by assert_safe
        connection.close()
        with psycopg.connect(
            dbname="postgres",
            host=db["HOST"],
            port=db["PORT"],
            user=db["USER"],
            password=db["PASSWORD"],
            autocommit=True,
        ) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
            ).fetchone()
            if exists and recreate:
                conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
                exists = None
            if not exists:
                conn.execute(f'CREATE DATABASE "{name}" TEMPLATE template_postgis')

    def log(self, message):
        self.stdout.write(f"[{time.time() - self.started:7.1f}s] {message}")

    def run_sql(self, label, sql):
        # No params: the SQL holds literal % operators and only trusted values.
        self.log(label)
        self.cursor.execute(sql)

    def create_model(self):
        for code, name in (("en", "English"), ("es", "Spanish")):
            Language.objects.get_or_create(code=code, defaults={"name": name})
        lifecycle = ResourceInstanceLifecycle.objects.create(name=c.LIFECYCLE_NAME)
        self.states = [
            ResourceInstanceLifecycleState.objects.create(
                name=name,
                action_label=name,
                resource_instance_lifecycle=lifecycle,
                is_initial_state=index == 0,
            )
            for index, name in enumerate(c.STATE_NAMES)
        ]
        options = [
            {"id": str(c.domain_option(k)), "text": {"en": f"Option {k}"}}
            for k in range(10)
        ]
        specs = (
            (c.STRING, "string", {}),
            (c.NUMBER, "number", {}),
            (c.DOMAIN, "domain-value-list", {"options": options}),
            (c.RESOURCE, "resource-instance", {}),
            (c.GEOMETRY, "geojson-feature-collection", {}),
        )
        graph_a = self.make_graph(c.GRAPH_A_SLUG, lifecycle)
        graph_b = self.make_graph(c.GRAPH_B_SLUG, lifecycle)
        for alias, datatype, config in specs:
            self.make_node(graph_a, alias, datatype, config)
            if alias in (c.STRING, c.GEOMETRY):
                self.make_node(graph_b, alias, datatype, config)
        boolean_group = NodeGroup.objects.create()
        for alias in c.BOOLEANS:
            self.make_node(
                graph_a,
                alias,
                "boolean",
                {"trueLabel": "Yes", "falseLabel": "No"},
                boolean_group,
            )
        return graph_a, graph_b

    @staticmethod
    def make_graph(slug, lifecycle):
        return GraphModel.objects.create(
            name=slug, slug=slug, isresource=True, resource_instance_lifecycle=lifecycle
        )

    @staticmethod
    def make_node(graph, alias, datatype, config, nodegroup=None):
        return Node.objects.create(
            name=alias,
            alias=alias,
            datatype=datatype,
            graph=graph,
            nodegroup=nodegroup or NodeGroup.objects.create(),
            istopnode=False,
            config=config,
        )

    def seed_resources(self, count_a, count_b, graphs):
        # The spatial-views trigger has nothing to update and the cardinality
        # check is redundant for generated data; both cost a query per tile.
        self.alter_triggers("DISABLE")
        try:
            for prefix, graph, count in (
                ("A", graphs[0], count_a),
                ("B", graphs[1], count_b),
            ):
                self.seed_graph(prefix, graph, c.get_nodes(graph.slug), count)
        finally:
            self.alter_triggers("ENABLE")
        self.refresh_geometries()

    def alter_triggers(self, action):
        for trigger in TRIGGERS:
            self.cursor.execute(f"ALTER TABLE tiles {action} TRIGGER {trigger}")

    def seed_graph(self, prefix, graph, nodes, count):
        series = f"generate_series(1, {count}) AS i"
        state_ids = ", ".join(f"'{state.pk}'" for state in self.states)
        self.run_sql(
            f"resources {prefix}",
            "INSERT INTO resource_instances (resourceinstanceid, graphid,"
            " resource_instance_lifecycle_state_id)"
            f" SELECT {c.resource_id_sql(prefix)}, '{graph.pk}',"
            f" (ARRAY[{state_ids}]::uuid[])"
            "[CASE WHEN i % 10 < 7 THEN 1 WHEN i % 10 < 9 THEN 2 ELSE 3 END]"
            f" FROM {series}",
        )
        bucketed = {
            c.STRING: (
                "jsonb_build_object(CASE WHEN i % 3 = 0 THEN 'es' ELSE 'en' END,"
                " jsonb_build_object('value', "
                + self.case(c.STRING_VALUES, "'other-' || (i % 500)")
                + ", 'direction', 'ltr'))"
            ),
            c.NUMBER: "to_jsonb("
            + self.case({b: c.NUMBER_VALUES[b] for b in c.BUCKETS}, "4", quote="")
            + ")",
            c.DOMAIN: "jsonb_build_array("
            + self.case(
                {
                    "high": c.domain_option(3),
                    "mid": c.domain_option(2),
                    "low": c.domain_option(1),
                },
                f"'{c.domain_option(0)}'",
            )
            + ")",
            c.RESOURCE: (
                "jsonb_build_array(jsonb_build_object('resourceId', "
                + self.case(
                    {b: c.resource_target(b) for b in c.BUCKETS},
                    "md5('A' || (5004 + i % 1000))::uuid::text",
                )
                + ", 'inverse', false, 'ontologyProperty', '',"
                " 'inverseOntologyProperty', ''))"
            ),
        }
        for alias, expr in bucketed.items():
            if prefix == "A" or alias == c.STRING:
                node = nodes[alias]
                self.insert_tiles(
                    f"{prefix}.{alias}",
                    node.nodegroup_id,
                    f"jsonb_build_object('{node.pk}', {expr})",
                    prefix,
                    series,
                    bucketed=True,
                )
        if prefix == "A":
            tests = (f"i % {c.HIGH_MOD} = 0", "i % 100 = 2", "i % 2 = 1")
            data = ", ".join(
                f"'{nodes[alias].pk}', to_jsonb({test})"
                for alias, test in zip(c.BOOLEANS, tests)
            )
            self.insert_tiles(
                f"{prefix}.booleans",
                nodes[c.BOOLEANS[0]].nodegroup_id,
                f"jsonb_build_object({data})",
                prefix,
                series,
            )
        geo = nodes[c.GEOMETRY]
        self.insert_tiles(
            f"{prefix}.geometry",
            geo.nodegroup_id,
            geometry_tiledata(prefix, geo.pk),
            prefix,
            series,
        )

    @staticmethod
    def case(values, default, quote="'"):
        branches = "".join(
            f" WHEN '{bucket}' THEN {quote}{value}{quote}"
            for bucket, value in values.items()
        )
        return f"CASE b{branches} ELSE {default} END"

    def insert_tiles(self, label, nodegroup_id, data, prefix, series, bucketed=False):
        source = f"(SELECT i, {BUCKET} AS b FROM {series}) s" if bucketed else series
        self.run_sql(
            f"tiles {label}",
            "INSERT INTO tiles (tileid, tiledata, nodegroupid, resourceinstanceid,"
            f" sortorder) SELECT md5('{label}' || i)::uuid, {data}, '{nodegroup_id}',"
            f" {c.resource_id_sql(prefix)}, 0 FROM {source}",
        )

    def refresh_geometries(self):
        # Arches fills geojson_geometries with refresh_geojson_geometries() (no
        # trigger does); this is its body limited to geometry nodes.
        self.run_sql(
            "geojson_geometries",
            """
            INSERT INTO geojson_geometries
                (tileid, resourceinstanceid, nodeid, geom, featureid)
            SELECT t.tileid, t.resourceinstanceid, n.nodeid,
                ST_Force2D(ST_Transform(ST_SetSRID((ST_Dump(ST_GeomFromGeoJSON(
                    (jsonb_array_elements(t.tiledata -> n.nodeid::text -> 'features')
                        -> 'geometry')::text))).geom, 4326), 3857)),
                (jsonb_array_elements(t.tiledata -> n.nodeid::text -> 'features')
                    ->> 'id')::uuid
            FROM tiles t JOIN nodes n ON t.nodegroupid = n.nodegroupid
            WHERE n.datatype = 'geojson-feature-collection'
            """,
        )

    def seed_sets(self, count):
        from arches_resource_sets.models import ResourceSet

        owner = User.objects.filter(is_superuser=True).first()
        owner = owner or User.objects.create_superuser(
            "abac_perf", "abac_perf@example.com", None
        )
        for size in (size for size in c.SET_SIZES if size <= count):
            resource_set = ResourceSet.objects.create(
                owner=owner, name={"en": f"abac-perf-{size}"}
            )
            self.run_sql(
                f"set {size}",
                "INSERT INTO resource_set_member"
                " (id, resource_set_id, resource_instance_id)"
                f" SELECT md5('m{size}-' || i)::uuid, '{resource_set.pk}',"
                f" {c.resource_id_sql('A', f'i * {count // size}')}"
                f" FROM generate_series(1, {size}) AS i",
            )

    def report(self, cursor):
        for table in c.COUNT_TABLES:
            cursor.execute(f"SELECT count(*) FROM {table}")
            self.log(f"{table}: {cursor.fetchone()[0]}")
