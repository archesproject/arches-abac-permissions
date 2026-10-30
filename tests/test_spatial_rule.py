import uuid

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.urls import reverse

from arches.app.models.models import (
    GeoJSONGeometry,
    MapLayer,
    MapSource,
    Node,
    NodeGroup,
    TileModel,
)
from tests.test_inclusion_rules import make_rule
from tests.test_views import ApiTestCase

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
}


class SpatialTestCase(ApiTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.geometry_nodegroup = NodeGroup.objects.create()
        cls.geometry_node, cls.other_geometry_node, cls.string_node = (
            Node.objects.create(
                name=name,
                alias=name,
                datatype=datatype,
                graph=cls.graph,
                nodegroup=cls.geometry_nodegroup,
                istopnode=False,
            )
            for name, datatype in (
                ("location", "geojson-feature-collection"),
                ("other_location", "geojson-feature-collection"),
                ("label", "string"),
            )
        )
        cls.inside = cls.make_resource(cls.graph, cls.active_state)
        cls.crossing = cls.make_resource(cls.graph, cls.active_state)
        cls.outside = cls.make_resource(cls.graph, cls.active_state)
        cls.other_node = cls.make_resource(cls.graph, cls.active_state)
        cls.add_geometry(cls.inside, cls.geometry_node, "POINT (5 5)")
        cls.add_geometry(cls.crossing, cls.geometry_node, "LINESTRING (-5 5, 5 5)")
        cls.add_geometry(cls.outside, cls.geometry_node, "POINT (20 20)")
        cls.add_geometry(cls.other_node, cls.other_geometry_node, "POINT (5 5)")

    @classmethod
    def add_geometry(cls, resource, node, wkt):
        tile = TileModel.objects.create(
            resourceinstance=resource,
            nodegroup=cls.geometry_nodegroup,
            data={},
            sortorder=0,
        )
        GeoJSONGeometry.objects.create(
            tile=tile,
            resourceinstance=resource,
            node=node,
            geom=GEOSGeometry(wkt, srid=4326),
        )

    def definition(self, geometry=SQUARE, node=None):
        return {
            "graphid": str(self.graph.pk),
            "nodeid": str((node or self.geometry_node).pk),
            "geometry": geometry,
        }

    def make_spatial_rule(self, **kwargs):
        return make_rule(
            modulename="spatial_rule.py",
            classname="SpatialRule",
            definition=self.definition(**kwargs),
        )


class SpatialRuleTests(SpatialTestCase):
    def test_matches_intersecting_geometries(self):
        rule = self.make_spatial_rule()
        rule.clean()
        self.assertEqual(
            set(rule.get_matching_resources()), {self.inside, self.crossing}
        )
        self.assertTrue(rule.matches_resource(self.inside))
        self.assertTrue(rule.matches_resource(self.crossing))
        self.assertFalse(rule.matches_resource(self.outside))
        self.assertFalse(rule.matches_resource(self.other_node))
        self.assertFalse(rule.matches_resource(self.other_graph_active))

    def test_multipolygon(self):
        rule = self.make_spatial_rule(
            geometry={
                "type": "MultiPolygon",
                "coordinates": [
                    [[[19, 19], [21, 19], [21, 21], [19, 21], [19, 19]]],
                    [[[40, 40], [41, 40], [41, 41], [40, 41], [40, 40]]],
                ],
            }
        )
        rule.clean()
        self.assertEqual(set(rule.get_matching_resources()), {self.outside})

    def test_overlapping_polygons(self):
        square = SQUARE["coordinates"]
        rule = self.make_spatial_rule(
            geometry={"type": "MultiPolygon", "coordinates": [square, square]}
        )
        rule.clean()
        self.assertEqual(
            set(rule.get_matching_resources()), {self.inside, self.crossing}
        )

    def test_crs_member_is_ignored(self):
        rule = self.make_spatial_rule(
            geometry={
                **SQUARE,
                "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
            }
        )
        self.assertTrue(rule.matches_resource(self.inside))

    def test_invalid_definitions(self):
        bowtie = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [10, 10], [10, 0], [0, 10], [0, 0]]],
        }
        too_many = {
            "type": "Polygon",
            "coordinates": [[[i * 1e-4, 0] for i in range(10001)] + [[0, 1], [0, 0]]],
        }
        for definition in (
            {},
            self.definition(geometry=None),
            {**self.definition(), "nodeid": str(uuid.uuid4())},
            {**self.definition(), "graphid": str(self.other_graph.pk)},
            self.definition(node=self.string_node),
            self.definition(geometry="POLYGON ((0 0, 1 0, 1 1, 0 0))"),
            self.definition(geometry={"type": "Point", "coordinates": [0, 0]}),
            self.definition(geometry={"type": "Polygon", "coordinates": "x"}),
            self.definition(geometry={"type": "Polygon", "coordinates": []}),
            self.definition(geometry=bowtie),
            self.definition(geometry=too_many),
            self.definition(
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 89], [0, 0]]],
                }
            ),
        ):
            with self.subTest(definition=str(definition)[:120]):
                rule = make_rule(
                    modulename="spatial_rule.py",
                    classname="SpatialRule",
                    definition=definition,
                )
                with self.assertRaises(ValidationError):
                    rule.clean()

    def test_index_sql(self):
        sql = self.make_spatial_rule().get_index_sql_for_rule()
        node = self.geometry_node
        self.assertIn(f"abac_geom_node_{node.pk.hex}", sql)
        self.assertIn("ON geojson_geometries USING gist (geom)", sql)
        self.assertIn(f"WHERE nodeid = '{node.pk}'", sql)


class SpatialApiTests(SpatialTestCase):
    def test_create_through_api(self):
        definition = self.definition()
        created = self.create_rule(rule_type="spatial", definition=definition)
        self.assertEqual(created["rule_type"], "spatial")
        self.assertEqual(created["definition"], definition)
        self.assertIn("geojson_geometries", created["index_sql"])

    def test_invalid_geometry_rejected(self):
        response = self.send(
            "post",
            reverse("abac_rules"),
            self.payload(
                rule_type="spatial",
                definition=self.definition(geometry={"type": "Point"}),
            ),
        )
        self.assertEqual(response.status_code, 400)

    def test_geometry_kept_as_text_for_other_rule_types(self):
        response = self.send(
            "post",
            reverse("abac_rules"),
            self.payload(
                rule_type="tile_node_value",
                definition={
                    "graphid": str(self.graph.pk),
                    "nodeid": str(self.string_node.pk),
                    "value": {"not": "text"},
                },
            ),
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["definition"]["value"], "{'not': 'text'}")

    def test_geometry_nodes(self):
        url = reverse("abac_resource_model_nodes", args=[self.graph.pk])
        nodes = self.client.get(url, {"datatype": "geojson-feature-collection"})
        self.assertEqual(
            {node["nodeid"] for node in nodes.json()["nodes"]},
            {str(self.geometry_node.pk), str(self.other_geometry_node.pk)},
        )
        response = self.client.get(url, {"datatype": "file-list"})
        self.assertEqual(response.status_code, 400)

    def test_map_config(self):
        MapSource.objects.create(
            name="abac-test-tiles",
            source={"type": "raster", "tiles": ["https://example.com/{z}/{x}/{y}"]},
        )
        MapLayer.objects.filter(name="streets").delete()
        MapLayer.objects.create(
            name="streets",
            isoverlay=False,
            icon="",
            layerdefinitions=[
                {"id": "abac-test", "type": "raster", "source": "abac-test-tiles"}
            ],
        )
        MapLayer.objects.create(
            name="Other basemap", isoverlay=False, icon="", layerdefinitions=[]
        )
        config = self.client.get(reverse("abac_map_config")).json()
        self.assertEqual(config["basemap"]["layers"][0]["id"], "abac-test")
        self.assertEqual(list(config["basemap"]["sources"]), ["abac-test-tiles"])
        self.assertIn("glyphs", config)
