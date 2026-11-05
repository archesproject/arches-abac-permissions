import uuid

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.urls import reverse

from arches.app.models.models import (
    GeoJSONGeometry,
    GraphModel,
    MapLayer,
    MapSource,
    Node,
    NodeGroup,
    TileModel,
)
from arches.app.models.tile import Tile
from arches_abac_permissions.rules.spatial_rule import parse_area
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
    def add_geometry(cls, resource, node, *wkts):
        tile = TileModel.objects.create(
            resourceinstance=resource,
            nodegroup=cls.geometry_nodegroup,
            data={},
            sortorder=0,
        )
        for wkt in wkts:
            GeoJSONGeometry.objects.create(
                tile=tile,
                resourceinstance=resource,
                node=node,
                geom=GEOSGeometry(wkt, srid=4326),
            )

    def definition(self, geometry=SQUARE, node=None, operator=None):
        definition = {
            "graphid": str(self.graph.pk),
            "nodeid": str((node or self.geometry_node).pk),
            "geometry": geometry,
        }
        if operator:
            definition["operator"] = operator
        return definition

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

    def test_operators(self):
        mostly_outside = self.make_resource(self.graph, self.active_state)
        self.add_geometry(mostly_outside, self.geometry_node, "LINESTRING (-20 5, 2 5)")
        partly_inside = self.make_resource(self.graph, self.active_state)
        self.add_geometry(
            partly_inside, self.geometry_node, "POINT (5 5)", "POINT (20 20)"
        )
        # Its centroid is in the area, but it doesn't touch it.
        ring = self.make_resource(self.graph, self.active_state)
        self.add_geometry(
            ring,
            self.geometry_node,
            "POLYGON ((-5 -5, 15 -5, 15 15, -5 15, -5 -5),"
            " (-1 -1, 11 -1, 11 11, -1 11, -1 -1))",
        )
        expected = {
            None: {self.inside, self.crossing, mostly_outside, partly_inside},
            "intersects": {self.inside, self.crossing, mostly_outside, partly_inside},
            "within": {self.inside},
            "centroid": {self.inside, self.crossing, partly_inside, ring},
        }
        candidates = {
            self.inside,
            self.crossing,
            self.outside,
            self.other_node,
            mostly_outside,
            partly_inside,
            ring,
        }
        for operator, matches in expected.items():
            with self.subTest(operator=operator):
                rule = self.make_spatial_rule(operator=operator)
                rule.clean()
                self.assertEqual(set(rule.get_matching_resources()), matches)
                for resource in candidates:
                    self.assertEqual(
                        rule.matches_resource(resource), resource in matches
                    )

    def test_geometry_refreshed_by_tile_writes(self):
        resource = self.make_resource(self.graph, self.active_state)

        def collection(x, y):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": str(uuid.uuid4()),
                        "properties": {},
                        "geometry": {"type": "Point", "coordinates": [x, y]},
                    }
                ],
            }

        node = str(self.geometry_node.pk)
        tile = TileModel.objects.create(
            resourceinstance=resource,
            nodegroup=self.geometry_nodegroup,
            data={node: collection(5, 5)},
            sortorder=0,
        )
        rule = self.make_spatial_rule()
        # Core refreshes geojson_geometries in after_update_all, not save().
        self.assertFalse(rule.matches_resource(resource))
        Tile.objects.get(pk=tile.pk).after_update_all()
        self.assertTrue(rule.matches_resource(resource))
        tile.data = {node: collection(20, 20)}
        tile.save()
        self.assertTrue(rule.matches_resource(resource))
        Tile.objects.get(pk=tile.pk).after_update_all()
        self.assertFalse(rule.matches_resource(resource))

    def test_area_is_parsed_once(self):
        parse_area.cache_clear()
        rule = self.make_spatial_rule()
        rule.matches_resource(self.inside)
        rule.matches_resource(self.outside)
        self.assertEqual(parse_area.cache_info().misses, 1)

    def test_draft_graph_rejected(self):
        draft = GraphModel.objects.create(
            name="Draft",
            slug="test_graph_draft",
            isresource=True,
            source_identifier=self.graph,
        )
        node = Node.objects.create(
            name="draft",
            alias="draft",
            datatype="geojson-feature-collection",
            graph=draft,
            nodegroup=NodeGroup.objects.create(),
            istopnode=False,
        )
        rule = make_rule(
            modulename="spatial_rule.py",
            classname="SpatialRule",
            definition={
                "graphid": str(draft.pk),
                "nodeid": str(node.pk),
                "geometry": SQUARE,
            },
        )
        with self.assertRaises(ValidationError):
            rule.clean()

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
            self.definition(operator="not intersects"),
            {**self.definition(), "graphid": "not-a-uuid"},
            # Crosses the antimeridian, so would be read as 340° wide.
            self.definition(
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [[170, 0], [-170, 0], [-170, 10], [170, 10], [170, 0]]
                    ],
                }
            ),
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
        self.assertEqual(
            created["definition"], {**definition, "operator": "intersects"}
        )
        self.assertIn("geojson_geometries", created["index_sql"])

    def test_geometry_is_normalised(self):
        definition = self.definition(
            geometry={
                **SQUARE,
                "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
                "bbox": [0, 0, 10, 10],
            },
            operator="within",
        )
        created = self.create_rule(rule_type="spatial", definition=definition)
        self.assertEqual(created["definition"]["geometry"], SQUARE)
        self.assertEqual(created["definition"]["operator"], "within")

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
        default = {node["datatype"] for node in self.client.get(url).json()["nodes"]}
        self.assertNotIn("geojson-feature-collection", default)

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
