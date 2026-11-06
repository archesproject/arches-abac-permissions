import json
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
from arches_abac_permissions.rules.spatial_rule import (
    MAX_BUFFER,
    SpatialRule,
    parse_area,
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

    def definition(self, geometry=SQUARE, node=None, operator=None, buffer=None):
        definition = {
            "graphid": str(self.graph.pk),
            "nodeid": str((node or self.geometry_node).pk),
            "geometry": geometry,
        }
        if buffer is not None:
            definition["buffer"] = buffer
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
            self.definition(geometry={"type": "Polygon", "coordinates": "x"}),
            self.definition(geometry={"type": "Polygon", "coordinates": []}),
            self.definition(geometry=bowtie),
            self.definition(geometry={"type": "Point", "coordinates": [0, 0]}),
            self.definition(
                geometry={"type": "Point", "coordinates": [0, 0]}, buffer=0
            ),
            self.definition(geometry={"type": "Circle", "coordinates": [0, 0]}),
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


class BufferedSpatialRuleTests(SpatialTestCase):
    POINT = {"type": "Point", "coordinates": [30, 0]}
    LINE = {"type": "LineString", "coordinates": [[40, 0], [41, 0]]}

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Near the equator one degree is about 111 km.
        cls.near_point = cls.make_resource(cls.graph, cls.active_state)
        cls.far_point = cls.make_resource(cls.graph, cls.active_state)
        cls.near_line = cls.make_resource(cls.graph, cls.active_state)
        cls.add_geometry(cls.near_point, cls.geometry_node, "POINT (30.3 0)")
        cls.add_geometry(cls.far_point, cls.geometry_node, "POINT (31 0)")
        cls.add_geometry(cls.near_line, cls.geometry_node, "POINT (40.5 0.2)")

    def matches(self, **kwargs):
        rule = self.make_spatial_rule(**kwargs)
        rule.clean()
        return set(rule.get_matching_resources())

    def test_buffered_point(self):
        self.assertEqual(
            self.matches(geometry=self.POINT, buffer=50000), {self.near_point}
        )
        self.assertEqual(
            self.matches(geometry=self.POINT, buffer=100000), {self.near_point}
        )

    def test_buffered_multipoint(self):
        geometry = {"type": "MultiPoint", "coordinates": [[30, 0], [31, 0]]}
        self.assertEqual(self.matches(geometry=geometry, buffer=1000), {self.far_point})

    def test_buffered_line(self):
        self.assertEqual(
            self.matches(geometry=self.LINE, buffer=30000), {self.near_line}
        )
        self.assertEqual(self.matches(geometry=self.LINE, buffer=1000), set())

    def test_mixed_collection(self):
        geometry = {
            "type": "GeometryCollection",
            "geometries": [SQUARE, self.POINT],
        }
        self.assertEqual(
            self.matches(geometry=geometry, buffer=50000),
            {self.inside, self.crossing, self.near_point},
        )

    def test_polygon_buffer_grows_area(self):
        # (11, 5) is outside the square, 111 km east of its edge at most.
        resource = self.make_resource(self.graph, self.active_state)
        self.add_geometry(resource, self.geometry_node, "POINT (10.5 5)")
        self.assertNotIn(resource, self.matches())
        self.assertIn(resource, self.matches(buffer=100000))
        plain = parse_area(json.dumps(SQUARE, sort_keys=True), 0)
        grown = parse_area(json.dumps(SQUARE, sort_keys=True), 100000)
        self.assertGreater(grown.area, plain.area)

    def test_many_parts_buffered_in_one_query(self):
        parse_area.cache_clear()
        geometry = {
            "type": "MultiPoint",
            "coordinates": [[index / 10, 0] for index in range(50)],
        }
        canonical = json.dumps(geometry, sort_keys=True)
        with self.assertNumQueries(1):
            area = parse_area(canonical, 1000)
        self.assertEqual(area.srid, 4326)
        self.assertIn(area.geom_type, ("Polygon", "MultiPolygon"))

    def test_operators_with_buffered_area(self):
        for operator in ("within", "centroid"):
            with self.subTest(operator=operator):
                self.assertEqual(
                    self.matches(geometry=self.POINT, buffer=50000, operator=operator),
                    {self.near_point},
                )

    def test_invalid_buffers(self):
        for buffer in (-1, "10", True, float("nan"), float("inf"), MAX_BUFFER + 1):
            with self.subTest(buffer=buffer):
                rule = self.make_spatial_rule(geometry=SQUARE, buffer=1)
                rule.definition["buffer"] = buffer
                with self.assertRaises(ValidationError):
                    rule.clean()

    def test_points_and_lines_need_a_buffer(self):
        for geometry in (
            self.POINT,
            self.LINE,
            {"type": "GeometryCollection", "geometries": [SQUARE, self.POINT]},
        ):
            for buffer in (None, 0):
                with self.subTest(geometry=geometry["type"], buffer=buffer):
                    rule = self.make_spatial_rule(geometry=geometry, buffer=buffer)
                    with self.assertRaises(ValidationError):
                        rule.clean()

    def test_buffer_past_limits_rejected(self):
        for geometry in (
            {"type": "Point", "coordinates": [0, 85]},
            {"type": "Point", "coordinates": [179.9, 0]},
        ):
            with self.subTest(geometry=geometry):
                rule = self.make_spatial_rule(geometry=geometry, buffer=50000)
                with self.assertRaises(ValidationError):
                    rule.clean()

    def test_invalid_collections_rejected(self):
        for geometry in (
            {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "GeometryCollection", "geometries": [self.POINT]}
                ],
            },
            {"type": "GeometryCollection", "geometries": "x"},
            {"type": "GeometryCollection", "geometries": ["x"]},
            {"type": "GeometryCollection", "geometries": [{"type": "Circle"}]},
            {"type": "GeometryCollection", "geometries": []},
        ):
            with self.subTest(geometry=str(geometry)):
                rule = self.make_spatial_rule(geometry=geometry, buffer=1000)
                with self.assertRaises(ValidationError):
                    rule.clean()

    def test_cache_distinguishes_buffers(self):
        parse_area.cache_clear()
        small = self.make_spatial_rule(geometry=self.POINT, buffer=1000)
        large = self.make_spatial_rule(geometry=self.POINT, buffer=2000)
        small.matches_resource(self.near_point)
        large.matches_resource(self.near_point)
        small.matches_resource(self.near_point)
        self.assertEqual(parse_area.cache_info().misses, 2)
        self.assertGreater(
            SpatialRule.parse_definition(large.definition)[1].area,
            SpatialRule.parse_definition(small.definition)[1].area,
        )

    def test_clean_definition_strips_extra_members(self):
        geometry = {
            "type": "GeometryCollection",
            "crs": "x",
            "geometries": [
                {**self.POINT, "bbox": [1], "crs": "x"},
                "not a dict",
            ],
        }
        cleaned = SpatialRule.clean_definition(
            {
                "graphid": "g",
                "nodeid": "n",
                "geometry": geometry,
                "buffer": 5,
                "extra": 1,
            },
            SpatialRule.rule_type.definition_keys,
        )
        self.assertEqual(
            cleaned["geometry"],
            {"type": "GeometryCollection", "geometries": [self.POINT, "not a dict"]},
        )
        self.assertEqual(cleaned["buffer"], 5)
        self.assertNotIn("extra", cleaned)
        self.assertNotIn(
            "buffer",
            SpatialRule.clean_definition(
                {"geometry": SQUARE}, SpatialRule.rule_type.definition_keys
            ),
        )

    def test_buffer_through_api(self):
        response = self.client.post(
            reverse("abac_rules"),
            data=json.dumps(
                {
                    "name": "Buffered",
                    "rule_type": "spatial",
                    "definition": self.definition(geometry=self.POINT, buffer=500),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["definition"]["buffer"], 500)


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
        MapLayer.objects.all().delete()
        MapSource.objects.create(
            name="abac-test-tiles",
            source={"type": "raster", "tiles": ["https://example.com/{z}/{x}/{y}"]},
        )
        MapSource.objects.create(name="abac-other", source={"type": "raster"})

        def layer(name, source, **kwargs):
            definitions = [{"id": f"{name}-id", "type": "raster", "source": source}]
            return MapLayer.objects.create(
                name=name,
                icon="",
                isoverlay=kwargs.pop("isoverlay", False),
                layerdefinitions=kwargs.pop("layerdefinitions", definitions),
                **kwargs,
            )

        layer("zeta", "abac-test-tiles", sortorder=1, addtomap=True)
        layer("alpha", "abac-other", sortorder=1)
        layer("first", "abac-other", sortorder=0)
        layer("empty", "abac-other", layerdefinitions=[])
        layer("junk", "abac-other", layerdefinitions=["x", None])
        layer("parcels", "abac-test-tiles", isoverlay=True)
        layer("noisy", "missing-source", isoverlay=True)
        config = self.client.get(reverse("abac_map_config")).json()
        self.assertNotIn("basemap", config)
        self.assertEqual(
            [entry["name"] for entry in config["basemaps"]],
            ["first", "alpha", "zeta"],
        )
        self.assertEqual(
            [entry["name"] for entry in config["overlays"]], ["noisy", "parcels"]
        )
        zeta = config["basemaps"][2]
        self.assertEqual(zeta["layers"][0]["id"], "zeta-id")
        self.assertEqual(list(zeta["sources"]), ["abac-test-tiles"])
        self.assertEqual(config["overlays"][0]["sources"], {})
        self.assertEqual(list(config["overlays"][1]["sources"]), ["abac-test-tiles"])
        self.assertIn("glyphs", config)
        # No streets: the first basemap added to the map wins.
        self.assertEqual(config["default_basemap"], "zeta")
        layer("streets", "abac-other", sortorder=5)
        config = self.client.get(reverse("abac_map_config")).json()
        self.assertEqual(config["default_basemap"], "streets")
        MapLayer.objects.filter(addtomap=True).update(addtomap=False)
        MapLayer.objects.filter(name="streets").delete()
        config = self.client.get(reverse("abac_map_config")).json()
        self.assertEqual(config["default_basemap"], "first")
        MapLayer.objects.filter(isoverlay=False).delete()
        config = self.client.get(reverse("abac_map_config")).json()
        self.assertIsNone(config["default_basemap"])
        self.assertEqual(config["basemaps"], [])
