import json
from unittest import mock, skipUnless

from django.contrib.auth.models import Group, Permission, User
from django.contrib.gis.geos import GEOSGeometry

from arches.app.models.models import GeoJSONGeometry, Node, NodeGroup, TileModel
from arches.app.search.elasticsearch_dsl_builder import Bool, Query
from arches.app.search.mappings import RESOURCES_INDEX
from arches.app.search.search_engine_factory import SearchEngineFactory
from arches_abac_permissions.models import InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.lifecycle_state_rule import LifecycleStateRule
from tests.test_inclusion_rules import LifecycleTestCase, make_rule
from tests.test_spatial_rule import SQUARE, SpatialTestCase

FRAMEWORK_LOGGER = (
    "arches_abac_permissions.permissions.arches_abac_permission_framework"
)


def elasticsearch_available():
    try:
        return SearchEngineFactory().create().es.ping()
    except Exception:
        return False


def dsl(search_filter):
    return json.loads(json.dumps(search_filter.dsl))


class SearchFilterTests(LifecycleTestCase):
    def test_lifecycle_rule(self):
        rule = self.make_lifecycle_rule()
        self.assertEqual(
            dsl(rule.get_search_filter_for_rule())["bool"]["filter"],
            [
                {"term": {"graph_id": str(self.graph.pk)}},
                {
                    "term": {
                        "resource_instance_lifecycle_state_id": str(
                            self.active_state.pk
                        )
                    }
                },
            ],
        )

    def test_rules_without_a_filter(self):
        rule = make_rule(
            modulename="tile_node_value_rule.py",
            classname="TileNodeValueRule",
            definition={},
        )
        self.assertIsNone(rule.get_search_filter_for_rule())


class PermissionSearchFilterTests(LifecycleTestCase):
    def setUp(self):
        self.framework = ArchesAbacPermissionFramework()
        self.group = Group.objects.create(name="searchers")
        self.user = User.objects.create(username="searcher")
        self.user.groups.add(self.group)

    def grant(self, rule, codename="view_resourceinstance"):
        grant = InclusionRuleGroupPermission.objects.create(rule=rule, group=self.group)
        grant.permissions.set(Permission.objects.filter(codename=codename))

    def rule_clauses(self):
        should = dsl(self.framework.get_permission_search_filter(self.user))["bool"][
            "filter"
        ][0]["bool"]["should"]
        # The first clause is the default-deny filter.
        return should[1:]

    def test_adds_filters_of_rules_granting_read(self):
        active = self.make_lifecycle_rule()
        self.grant(active)
        self.assertEqual(
            self.rule_clauses(), [dsl(active.get_search_filter_for_rule())]
        )

    def test_ignores_other_grants_and_rules(self):
        self.grant(self.make_lifecycle_rule(), codename="change_resourceinstance")
        inactive = self.make_lifecycle_rule(state=self.draft_state)
        inactive.active = False
        inactive.save()
        self.grant(inactive)
        self.grant(
            make_rule(
                modulename="tile_node_value_rule.py", classname="TileNodeValueRule"
            )
        )
        other_group = Group.objects.create(name="others")
        InclusionRuleGroupPermission.objects.create(
            rule=self.make_lifecycle_rule(), group=other_group
        ).permissions.set(Permission.objects.filter(codename="view_resourceinstance"))
        self.assertEqual(self.rule_clauses(), [])

    def test_skips_an_empty_filter(self):
        self.grant(self.make_lifecycle_rule())
        with mock.patch.object(
            LifecycleStateRule, "get_search_filter", return_value=Bool()
        ):
            self.assertEqual(self.rule_clauses(), [])

    def test_skips_a_broken_rule(self):
        broken = self.make_lifecycle_rule()
        broken.definition = {}
        broken.save()
        self.grant(broken)
        with self.assertLogs(FRAMEWORK_LOGGER):
            self.assertEqual(self.rule_clauses(), [])


class SiteTestCase(SpatialTestCase):
    """Geometries in a nodegroup of their own, as search needs."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.site_nodegroup = NodeGroup.objects.create()
        cls.site_node = Node.objects.create(
            name="site",
            alias="site",
            datatype="geojson-feature-collection",
            graph=cls.graph,
            nodegroup=cls.site_nodegroup,
            istopnode=False,
        )
        cls.sites = {
            "inside": ["POINT (5 5)"],
            "crossing": ["LINESTRING (-5 5, 5 5)"],
            "partly": ["POINT (5 5)", "POINT (20 20)"],
            "outside": ["POINT (20 20)"],
        }
        cls.site_resources = {}
        for name, wkts in cls.sites.items():
            resource = cls.make_resource(cls.graph, cls.active_state)
            cls.site_resources[name] = resource
            tile = TileModel.objects.create(
                resourceinstance=resource,
                nodegroup=cls.site_nodegroup,
                data={},
                sortorder=0,
            )
            for wkt in wkts:
                GeoJSONGeometry.objects.create(
                    tile=tile,
                    resourceinstance=resource,
                    node=cls.site_node,
                    geom=GEOSGeometry(wkt, srid=4326),
                )


class SpatialSearchFilterTests(SiteTestCase):
    def test_centroid_has_no_filter(self):
        rule = self.make_spatial_rule(node=self.site_node, operator="centroid")
        self.assertIsNone(rule.get_search_filter_for_rule())

    def test_node_sharing_its_nodegroup_has_no_filter(self):
        # The search index can't tell geometry nodes in one nodegroup apart.
        rule = self.make_spatial_rule()
        self.assertIsNone(rule.get_search_filter_for_rule())


@skipUnless(elasticsearch_available(), "Elasticsearch is not available")
class SpatialSearchFilterElasticsearchTests(SiteTestCase):
    """Search finds the same resources as the rule's SQL."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        se = SearchEngineFactory().create()
        for name, resource in cls.site_resources.items():
            features = [
                {"type": "Feature", "geometry": json.loads(GEOSGeometry(wkt).geojson)}
                for wkt in cls.sites[name]
            ]
            se.index_data(
                index=RESOURCES_INDEX,
                id=str(resource.pk),
                body={
                    "resourceinstanceid": str(resource.pk),
                    "graph_id": str(cls.graph.pk),
                    "geometries": [
                        {
                            "geom": {"type": "FeatureCollection", "features": features},
                            "nodegroup_id": str(cls.site_nodegroup.pk),
                            "provisional": False,
                        }
                    ],
                },
            )
        se.refresh(index=RESOURCES_INDEX)

    @classmethod
    def tearDownClass(cls):
        for resource in cls.site_resources.values():
            SearchEngineFactory().create().delete(
                index=RESOURCES_INDEX, id=str(resource.pk)
            )
        super().tearDownClass()

    def search(self, search_filter):
        query = Query(SearchEngineFactory().create(), start=0, limit=100)
        query.add_query(search_filter)
        hits = query.search(index=RESOURCES_INDEX)["hits"]["hits"]
        return {hit["_id"] for hit in hits}

    def test_search_matches_sql(self):
        expected = {
            "intersects": {"inside", "crossing", "partly"},
            "within": {"inside"},
        }
        for operator, names in expected.items():
            with self.subTest(operator=operator):
                rule = self.make_spatial_rule(
                    node=self.site_node, operator=operator, geometry=SQUARE
                )
                sql = {
                    str(pk)
                    for pk in rule.get_matching_resources().values_list("pk", flat=True)
                }
                self.assertEqual(
                    sql, {str(self.site_resources[name].pk) for name in names}
                )
                self.assertEqual(self.search(rule.get_search_filter_for_rule()), sql)
