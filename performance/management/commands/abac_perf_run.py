import json
from collections import deque
import math
import statistics
import time
from dataclasses import dataclass
from typing import Callable

from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext

from arches.app.models.models import (
    GeoJSONGeometry,
    Language,
    ResourceInstance,
)
from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from performance import common as c

PREFIX = "perf:"
VIEW_PERMISSION = "models.view_resourceinstance"
GROUPS = ("lifecycle_state", "resource_set", "tile_node_value", "spatial", "framework")
RANK = {"high": 0, "mid": 1, "low": 2}
SLOW_MS = 2000  # one slow run -> stop after 2 runs
PAGE = 25

# Resource indexes i of the seed that hold each bucket's value (and none of them).
HIT_I = {"high": c.HIGH_MOD, "mid": 2, "low": 1}
HIT_I_ES = {"high": 3 * c.HIGH_MOD, "mid": 102, "low": 3}
MISS_I = 4
OPTION_FOR_BUCKET = {"high": 3, "mid": 2, "low": 1}


@dataclass
class Case:
    group: str
    name: str
    selectivity: str
    rule: InclusionRule
    hit: Callable = None
    miss: Callable = None


def resource(index, prefix="A"):
    return ResourceInstance.objects.get(pk=c.hash_uuid(f"{prefix}{index}"))


def square(x, y, size_x, size_y):
    ring = [[x, y], [x + size_x, y], [x + size_x, y + size_y], [x, y + size_y], [x, y]]
    return {"type": "Polygon", "coordinates": [ring]}


def circle(cx, cy, radius, segments=9999):
    ring = [
        [
            cx + radius * math.cos(2 * math.pi * k / segments),
            cy + radius * math.sin(2 * math.pi * k / segments),
        ]
        for k in range(segments)
    ]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def make_rule(module, classname, name, definition):
    rule = InclusionRule(
        name=PREFIX + name,
        modulename=f"{module}.py",
        classname=classname,
        definition=definition,
    )
    rule.full_clean(exclude=["owner"])  # validates and stores the server-derived keys
    rule.save()
    return rule


def summarize_plan(plan):
    """Key facts of an EXPLAIN (FORMAT JSON) plan."""
    scans, nodes = [], []

    def walk(node):
        nodes.append(node["Node Type"])
        if "Relation Name" in node or "Index Name" in node:
            scans.append(
                {
                    "type": node["Node Type"],
                    "relation": node.get("Relation Name"),
                    "index": node.get("Index Name"),
                    "rows": node.get("Actual Rows"),
                    "loops": node.get("Actual Loops"),
                    "ms": round(node.get("Actual Total Time", 0), 2),
                }
            )
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    return {
        "execution_ms": plan.get("Execution Time"),
        "planning_ms": plan.get("Planning Time"),
        "shared_hit": plan["Plan"].get("Shared Hit Blocks"),
        "shared_read": plan["Plan"].get("Shared Read Blocks"),
        "seq_scans": [s["relation"] for s in scans if s["type"] == "Seq Scan"],
        "scans": scans,
        "nodes": nodes,
    }


class Command(BaseCommand):
    help = "Benchmark ABAC rule types against the seeded abac_perf database."

    def add_arguments(self, parser):
        parser.add_argument("--size", choices=c.SIZES, default="1k")
        parser.add_argument("--repeat", type=int, default=5)
        parser.add_argument("--output", default="abac-perf-results.json")
        parser.add_argument("--only", choices=GROUPS)
        parser.add_argument("--with-indexes", action="store_true")
        parser.add_argument("--without-indexes", action="store_true")
        parser.add_argument(
            "--resume", action="store_true", help="keep and skip results in --output"
        )
        parser.add_argument("--timeout", type=int, default=180, help="seconds")
        parser.add_argument(
            "--framework-counts",
            default="0,1,5,20",
            help="comma-separated rule counts for the framework cases",
        )
        parser.add_argument(
            "--ops",
            help="comma-separated op name prefixes to run (e.g. matches_,e_,f_)",
        )

    # ---- harness plumbing -------------------------------------------------

    def handle(self, *args, **options):
        c.assert_safe(options["size"])
        self.repeat = options["repeat"]
        self.results = []
        self.output = options["output"]
        if options["resume"]:
            with open(self.output) as handle:
                self.results = json.load(handle)["results"]
        self.done = {
            (r.get("variant"), r["group"], r["case"], r["op"])
            for r in self.results
            if "error" not in r
        }
        self.checked = set()
        self.variant = None
        self.only = options["only"]
        self.ops = tuple(options["ops"].split(",")) if options["ops"] else None
        self.framework_counts = [int(n) for n in options["framework_counts"].split(",")]
        self.fw = ArchesAbacPermissionFramework()
        with connection.cursor() as cursor:
            cursor.execute(f"SET statement_timeout = '{options['timeout']}s'")
        self.cleanup()  # leftovers from an interrupted run
        self.setup()
        variants = []
        if options["without_indexes"] or not options["with_indexes"]:
            variants.append("without_indexes")
        if options["with_indexes"] or not options["without_indexes"]:
            variants.append("with_indexes")
        started = time.time()
        meta = self.meta = {"environment": self.environment(), "repeat": self.repeat}
        try:
            self.drop_abac_indexes()
            for variant in variants:
                self.variant = variant
                if variant == "with_indexes":
                    meta["index_builds"] = self.create_indexes()
                self.run_variant()
        finally:
            self.drop_abac_indexes()
            self.cleanup()
        meta["existing_indexes"] = self.existing_indexes()
        meta["wall_seconds"] = round(time.time() - started)
        self.save()
        self.stdout.write(f"wrote {self.output}")

    def save(self):
        with open(self.output, "w") as handle:
            json.dump(
                {"meta": self.meta, "results": self.results},
                handle,
                default=str,
                indent=1,
            )

    def wants(self, group):
        return self.only in (None, group)

    def record(self, group, name, op, fn, plan=False, repeat=None):
        """Time fn (warm), count its queries and optionally EXPLAIN its slowest query."""
        entry = {"group": group, "case": name, "op": op, "variant": self.variant}
        if (self.variant, group, name, op) in self.done:
            return
        if self.ops and not op.startswith(self.ops):
            return
        try:
            times = []
            limit = repeat or self.repeat
            while len(times) < limit - 1:
                start = time.perf_counter()
                fn()
                times.append((time.perf_counter() - start) * 1000)
                if times[0] > SLOW_MS:
                    break
            # The captured run is the last timed run (query count + plan source).
            connection.queries_log = deque(maxlen=1_000_000)
            start = time.perf_counter()
            with CaptureQueriesContext(connection) as queries:
                value = fn()
            times.append((time.perf_counter() - start) * 1000)
            entry.update(
                median_ms=round(statistics.median(times), 2),
                max_ms=round(max(times), 2),
                runs=len(times),
                queries=len(queries),
            )
            if isinstance(value, int) and not isinstance(value, bool):
                entry["value"] = value
            if plan:
                entry.update(self.explain(queries))
        except DatabaseError as error:
            entry["error"] = str(error).splitlines()[0]
        self.results.append(entry)
        self.save()
        self.stdout.write(
            f"{self.variant} {group}/{name}/{op}: "
            + (
                f"{entry['median_ms']}ms runs={entry['runs']} q={entry['queries']}"
                if "median_ms" in entry
                else f"ERROR {entry['error']}"
            )
        )

    @staticmethod
    def explain(queries):
        selects = [
            q
            for q in queries.captured_queries
            if q["sql"].lstrip().startswith(("SELECT", "(SELECT", "WITH"))
        ]
        if not selects:
            return {}
        slowest = max(selects, key=lambda q: float(q["time"]))
        with connection.cursor() as cursor:
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + slowest["sql"])
            plan = cursor.fetchone()[0][0]
        return {"plan_summary": summarize_plan(plan), "plan": plan}

    def sql(self, statement, fetch=False):
        with connection.cursor() as cursor:
            cursor.execute(statement)
            return cursor.fetchall() if fetch else None

    # ---- environment ------------------------------------------------------

    def environment(self):
        import arches
        import arches_abac_permissions

        versions = self.sql("SELECT version(), postgis_full_version()", fetch=True)[0]
        counts = {
            table: self.sql(f"SELECT count(*) FROM {table}", fetch=True)[0][0]
            for table in c.COUNT_TABLES
        }
        sizes = {
            table: self.sql(
                f"SELECT pg_size_pretty(pg_total_relation_size('{table}'))", fetch=True
            )[0][0]
            for table in ("resource_instances", "tiles", "geojson_geometries")
        }
        settings = {
            name: self.sql(f"SHOW {name}", fetch=True)[0][0]
            for name in ("shared_buffers", "work_mem", "effective_cache_size")
        }
        return {
            "arches": arches.__version__ if hasattr(arches, "__version__") else None,
            "arches_path": arches.__file__,
            "abac_path": arches_abac_permissions.__file__,
            "postgres": versions[0],
            "postgis": versions[1],
            "row_counts": counts,
            "table_sizes": sizes,
            "pg_settings": settings,
        }

    def existing_indexes(self):
        rows = self.sql(
            "SELECT tablename, indexname, indexdef,"
            " pg_relation_size(quote_ident(indexname)::regclass) FROM pg_indexes"
            " WHERE tablename IN ('resource_instances','tiles','geojson_geometries')"
            " ORDER BY 1, 2",
            fetch=True,
        )
        return [dict(zip(("table", "name", "def", "bytes"), row)) for row in rows]

    # ---- indexes ----------------------------------------------------------

    def drop_abac_indexes(self):
        for (name,) in self.sql(
            "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'abac\\_%'",
            fetch=True,
        ):
            self.sql(f"DROP INDEX {name}")

    def create_indexes(self):
        statements = {}
        for case in self.cases:
            statement = case.rule.get_index_sql_for_rule()
            if statement:
                statements[statement] = None
        builds = []
        for statement in statements:
            start = time.time()
            self.sql(statement)
            builds.append({"sql": statement, "seconds": round(time.time() - start, 1)})
            self.stdout.write(
                f"index built in {builds[-1]['seconds']}s: {statement.splitlines()[0]}"
            )
        for table in ("resource_instances", "tiles", "geojson_geometries"):
            self.sql(f"ANALYZE {table}")
        for build in builds:
            name = build["sql"].split("EXISTS ")[1].split()[0]
            build["bytes"] = self.sql(
                f"SELECT pg_relation_size('{name}'::regclass)", fetch=True
            )[0][0]
        return builds

    # ---- fixtures ---------------------------------------------------------

    def setup(self):
        self.graph_a = c.get_graph(c.GRAPH_A_SLUG)
        self.graph_b = c.get_graph(c.GRAPH_B_SLUG)
        self.nodes = c.get_nodes(c.GRAPH_A_SLUG)
        self.nodes_b = c.get_nodes(c.GRAPH_B_SLUG)
        states = (
            self.graph_a.resource_instance_lifecycle.resource_instance_lifecycle_states
        )
        self.states = [states.get(name=name) for name in c.STATE_NAMES]
        self.cases = []
        self.add_lifecycle_cases()
        self.add_set_cases()
        self.add_tile_cases()
        self.add_spatial_cases()
        self.setup_framework_rules()

    def cleanup(self):
        InclusionRule.objects.filter(name__startswith=PREFIX).delete()
        User.objects.filter(username=f"{PREFIX}user").delete()
        Group.objects.filter(name=f"{PREFIX}group").delete()
        Language.objects.filter(code__startswith="zz").delete()

    def add(self, group, name, selectivity, module, classname, definition, **kwargs):
        rule = make_rule(module, classname, f"{group}/{name}", definition)
        case = Case(group, name, selectivity, rule, **kwargs)
        self.cases.append(case)
        return case

    def add_lifecycle_cases(self):
        # i % 10 < 7 -> Draft, 7-8 -> Active, 9 -> Retired
        index_of_state = (1, 7, 9)
        selectivity = ("low", "mid", "mid")
        for k, state in enumerate(self.states):
            for label, graph in (("A", self.graph_a), ("B", self.graph_b)):
                if label == "B" and k != 0:
                    continue
                self.add(
                    "lifecycle_state",
                    f"{label}:{state.name}",
                    selectivity[k],
                    "lifecycle_state_rule",
                    "LifecycleStateRule",
                    {"graphid": str(graph.pk), "lifecycle_state_id": str(state.pk)},
                    hit=lambda i=index_of_state[k], p=label: resource(i, p),
                    miss=lambda i=index_of_state[(k + 1) % 3], p=label: resource(i, p),
                )

    def add_set_cases(self):
        from arches_resource_sets.models import ResourceSet

        sets = ResourceSet.objects.annotate(size=Count("resourcesetmember"))
        for resource_set in sorted(sets, key=lambda s: s.size):
            if not str(resource_set.name).startswith("abac-perf-"):
                continue
            step = c.RESOURCES // resource_set.size
            self.add(
                "resource_set",
                f"{resource_set.size}",
                c.BUCKETS[c.SET_SIZES.index(resource_set.size)],
                "resource_set_rule",
                "ResourceSetRule",
                {"resource_set_id": str(resource_set.pk)},
                hit=lambda s=step: resource(s),
                miss=lambda: resource(1),
            )

    def add_tile_cases(self):
        langs = (("en", HIT_I), ("es", HIT_I_ES), ("", HIT_I))
        for bucket in c.BUCKETS:
            for language, hits in langs:
                self.add_tile(
                    f"str:{bucket}:{language or 'any'}",
                    bucket,
                    c.STRING,
                    c.STRING_VALUES[bucket],
                    hits[bucket],
                    language=language,
                )
            self.add_tile(f"num:{bucket}", bucket, c.NUMBER, c.NUMBER_VALUES[bucket])
            self.add_tile(
                f"dvl:{bucket}",
                bucket,
                c.DOMAIN,
                str(c.domain_option(OPTION_FOR_BUCKET[bucket])),
            )
            self.add_tile(
                f"ri:{bucket}", bucket, c.RESOURCE, str(c.resource_target(bucket))
            )
            self.add_tile(f"bool:{bucket}", bucket, f"bool_{bucket}", "true")

    def add_tile(self, name, bucket, alias, value, hit_index=None, **definition):
        node = self.nodes[alias]
        rule_definition = {
            "graphid": str(self.graph_a.pk),
            "nodeid": str(node.pk),
            "value": value,
            **definition,
        }
        self.add(
            "tile_node_value",
            name,
            bucket,
            "tile_node_value_rule",
            "TileNodeValueRule",
            rule_definition,
            hit=lambda: resource(hit_index or HIT_I[bucket]),
            miss=lambda: resource(MISS_I),
        )

    def add_spatial_cases(self):
        areas = {
            "small": ("high", square(3.0, 3.0, 0.1, 0.1)),
            "medium": ("mid", square(3.0, 3.0, 1.0, 1.0)),
            "large": ("low", square(0.0, 0.0, 10.0, 5.0)),
        }
        for operator in ("intersects", "within", "centroid"):
            for size, (selectivity, area) in areas.items():
                self.add_spatial(f"{operator}:{size}", selectivity, operator, area)
            self.add_spatial(
                f"{operator}:circle10k", "mid", operator, circle(5.0, 5.0, 0.5642)
            )
        point = {"type": "Point", "coordinates": [5.0, 5.0]}
        self.add_spatial("intersects:buffer11km", "high", "intersects", point, 11000)
        self.add_spatial("intersects:buffer100km", "mid", "intersects", point, 100000)

    def add_spatial(self, name, selectivity, operator, area, buffer=None):
        definition = {
            "graphid": str(self.graph_a.pk),
            "nodeid": str(self.nodes[c.GEOMETRY].pk),
            "geometry": area,
            "operator": operator,
        }
        if buffer:
            definition["buffer"] = buffer
        case = self.add(
            "spatial", name, selectivity, "spatial_rule", "SpatialRule", definition
        )
        case.hit = lambda r=case.rule: list(r.get_matching_resources()[:1])[0]
        case.miss = lambda r=case.rule: self.spatial_miss(r)

    def spatial_miss(self, rule):
        node, area, _operator = rule.get_class_module().parse_definition(
            rule.definition
        )
        candidates = GeoJSONGeometry.objects.filter(node=node).exclude(
            geom__intersects=area
        )[:20]
        for geometry in candidates:
            if not rule.matches_resource(geometry.resourceinstance):
                return geometry.resourceinstance
        raise CommandError(f"No non-matching resource for {rule.name}")

    # ---- per-rule benchmarks ----------------------------------------------

    def run_variant(self):
        for case in self.cases:
            if self.wants(case.group):
                self.run_case(case)
        if self.wants("tile_node_value"):
            self.run_language_scaling()
        if self.wants("framework"):
            self.run_framework()

    def run_case(self, case):
        rule = case.rule
        try:
            hit, miss = case.hit(), case.miss()
        except (DatabaseError, IndexError) as error:  # no hit in small datasets
            self.results.append(
                {
                    "group": case.group,
                    "case": case.name,
                    "variant": self.variant,
                    "op": "setup",
                    "error": str(error).splitlines()[0],
                }
            )
            self.stdout.write(f"{self.variant} {case.name}: SETUP ERROR {error}")
            return
        if case.name not in self.checked:
            self.checked.add(case.name)
            self.sanity(case, hit, miss)
        ops = {
            "matches_hit": (lambda: rule.matches_resource(hit), False),
            "matches_miss": (lambda: rule.matches_resource(miss), False),
            "count": (lambda: rule.get_matching_resources().count(), True),
            "page25": (lambda: len(list(rule.get_matching_resources()[:PAGE])), True),
        }
        for op, (fn, plan) in ops.items():
            self.record(case.group, case.name, op, fn, plan=plan)

    def sanity(self, case, hit, miss):
        if not case.rule.matches_resource(hit) or case.rule.matches_resource(miss):
            self.stdout.write(f"WARNING: hit/miss resources wrong for {case.name}")
            self.results.append(
                {"group": case.group, "case": case.name, "op": "sanity_failed"}
            )

    def run_language_scaling(self):
        # Any-language string rules OR one @> per Language row.
        for extra in (0, 8):
            rule = None
            codes = [f"zz{k}" for k in range(extra)]
            for code in codes:
                Language.objects.get_or_create(code=code, defaults={"name": code})
            try:
                rule = make_rule(
                    "tile_node_value_rule",
                    "TileNodeValueRule",
                    "lang-scaling",
                    {
                        "graphid": str(self.graph_a.pk),
                        "nodeid": str(self.nodes[c.STRING].pk),
                        "value": c.STRING_VALUES["mid"],
                    },
                )
                name = f"str:mid:any:{Language.objects.count()}languages"
                self.record(
                    "tile_node_value",
                    name,
                    "count",
                    lambda: rule.get_matching_resources().count(),
                    plan=True,
                )
            finally:
                Language.objects.filter(code__in=codes).delete()
                if rule:
                    rule.delete()

    # ---- framework --------------------------------------------------------

    def setup_framework_rules(self):
        pools = {}
        for case in self.cases:
            pools.setdefault(case.group, []).append(case)
        for pool in pools.values():
            pool.sort(key=lambda case: RANK[case.selectivity])
        # Round-robin across rule types, most selective first.
        self.mix_cases = []
        for position in range(max(len(pool) for pool in pools.values())):
            for pool in pools.values():
                if position < len(pool):
                    self.mix_cases.append(pool[position])
        self.mix_cases = self.mix_cases[: max(self.framework_counts)]
        self.user = User.objects.create_user(f"{PREFIX}user")
        self.group = Group.objects.create(name=f"{PREFIX}group")
        self.user.groups.add(self.group)
        permission = Permission.objects.get(
            codename="view_resourceinstance", content_type__app_label="models"
        )
        for case in self.mix_cases:
            grant = InclusionRuleGroupPermission.objects.create(
                rule=case.rule, group=self.group
            )
            grant.permissions.add(permission)
            InclusionRule.objects.filter(pk=case.rule.pk).update(active=False)

    def activate(self, count):
        for position, case in enumerate(self.mix_cases):
            InclusionRule.objects.filter(pk=case.rule.pk).update(
                active=position < count
            )
        return [case.rule for case in self.mix_cases[:count]]

    def run_framework(self):
        fw, user = self.fw, self.user
        queryset = lambda: fw.filter_resource_queryset(
            user, ResourceInstance.objects.all()
        )
        abac = lambda: fw.get_abac_resources(user, VIEW_PERMISSION)
        by_graph = lambda graph, n: list(
            ResourceInstance.objects.filter(graph=graph).order_by("pk")[:n]
        )
        populations = {
            "A25": by_graph(self.graph_a, 25),
            "A1000": by_graph(self.graph_a, 1000),
            "B25": by_graph(self.graph_b, 25),
        }
        for count in self.framework_counts:
            rules = self.activate(count)
            name = f"{count}rules"
            describe = ",".join(r.name[len(PREFIX) :] for r in rules)
            self.stdout.write(f"{name}: {describe}")
            ops = {
                "c_filter_count": (lambda: queryset().count(), True),
                "c_filter_page25": (lambda: len(list(queryset()[:PAGE])), True),
                "d_abac_resources_count": (lambda: abac().count(), True),
                "d_abac_resources_page25": (lambda: len(list(abac()[:PAGE])), True),
            }
            if rules:
                ops["d_union_count"] = (lambda: self.union(rules, True), True)
                ops["d_union_page25"] = (lambda: self.union(rules, False), True)
            for op, (fn, plan) in ops.items():
                self.record("framework", name, op, fn, plan=plan)
            for label, resources in populations.items():
                self.record(
                    "framework",
                    name,
                    f"e_get_perms_{label}",
                    lambda r=resources: sum(len(fw.get_perms(user, x)) for x in r),
                    repeat=1 if len(resources) > PAGE else None,
                )
            if count == max(self.framework_counts):
                for label in ("A25", "B25"):
                    self.record(
                        "framework",
                        name,
                        f"f_user_can_read_{label}",
                        lambda t=populations[label][0]: fw.user_can_read_resource(
                            user, resource=t
                        ),
                    )
        self.activate(0)

    def union(self, rules, count):
        """UNION of the rules' matching pks instead of an OR of pk__in subqueries."""
        parts, params = [], []
        for rule in rules:
            sql, rule_params = (
                rule.get_matching_resources().values("pk").query.sql_with_params()
            )
            parts.append(f"({sql})")
            params.extend(rule_params)
        select = "count(*)" if count else "resourceinstanceid"
        tail = "" if count else f" LIMIT {PAGE}"
        statement = (
            f"SELECT {select} FROM resource_instances WHERE resourceinstanceid IN ("
            + " UNION ".join(parts)
            + f"){tail}"
        )
        with connection.cursor() as cursor:
            cursor.execute(statement, params)
            rows = cursor.fetchall()
        return rows[0][0] if count else len(rows)
