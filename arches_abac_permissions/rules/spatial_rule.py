import json

from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from arches.app.models.models import (
    GeoJSONGeometry,
    GraphModel,
    Node,
    ResourceInstance,
)
from arches_abac_permissions.models import InclusionRule

GEOMETRY_DATATYPE = "geojson-feature-collection"
GEOMETRY_TYPES = ("Polygon", "MultiPolygon")
MAX_VERTICES = 10000
# Geometries are stored in EPSG:3857, which is undefined beyond this latitude.
MAX_LATITUDE = 85.05112878


class SpatialRule(InclusionRule):
    """
    Rule matching resources whose geometry node intersects an area.

    definition: {
        "graphid": "<graph id>",
        "nodeid": "<geojson-feature-collection node id>",
        "geometry": <GeoJSON Polygon or MultiPolygon in EPSG:4326>
    }

    Evaluated against the geojson_geometries table, so arches-search isn't
    required.
    """

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        node, area = cls.parse_definition(inclusion_rule.definition)
        geometries = GeoJSONGeometry.objects.filter(node=node, geom__intersects=area)
        return ResourceInstance.objects.filter(
            pk__in=geometries.values("resourceinstance_id")
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        node, area = cls.parse_definition(inclusion_rule.definition)
        if resource.graph_id != node.graph_id:
            return False
        return GeoJSONGeometry.objects.filter(
            node=node, resourceinstance=resource, geom__intersects=area
        ).exists()

    @classmethod
    def validate_definition(cls, inclusion_rule):
        cls.parse_definition(inclusion_rule.definition)

    @classmethod
    def get_index_sql(cls, inclusion_rule):
        node, _area = cls.parse_definition(inclusion_rule.definition)
        # Ids come from the database, so formatting them into SQL is safe.
        return (
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS abac_geom_node_{node.pk.hex}\n"
            f"    ON geojson_geometries USING gist (geom)\n"
            f"    WHERE nodeid = '{node.pk}';"
        )

    @classmethod
    def parse_definition(cls, definition):
        """Return the geometry node and the area as a GEOSGeometry."""
        graphid = definition.get("graphid")
        nodeid = definition.get("nodeid")
        geometry = definition.get("geometry")
        if not graphid or not nodeid or not geometry:
            raise ValidationError(
                _("Spatial rules require a 'graphid', a 'nodeid' and a 'geometry'.")
            )
        try:
            graph = GraphModel.objects.get(pk=graphid, isresource=True)
        except (GraphModel.DoesNotExist, ValidationError):
            raise ValidationError(_("%s is not the id of a resource model.") % graphid)
        try:
            node = Node.objects.get(pk=nodeid, graph=graph)
        except (Node.DoesNotExist, ValidationError):
            raise ValidationError(
                _("%(nodeid)s is not the id of a node of graph %(graphid)s.")
                % {"nodeid": nodeid, "graphid": graphid}
            )
        if node.datatype != GEOMETRY_DATATYPE:
            raise ValidationError(_("The node must be a geometry node."))
        return node, cls.parse_geometry(geometry)

    @staticmethod
    def parse_geometry(geometry):
        if not isinstance(geometry, dict) or geometry.get("type") not in GEOMETRY_TYPES:
            raise ValidationError(_("The area must be a Polygon or MultiPolygon."))
        # Only type and coordinates are read, so a "crs" member can't
        # reinterpret the coordinates.
        try:
            area = GEOSGeometry(
                json.dumps(
                    {
                        "type": geometry["type"],
                        "coordinates": geometry.get("coordinates"),
                    }
                ),
                srid=4326,
            )
        except (GEOSException, GDALException, ValueError, TypeError):
            raise ValidationError(_("The area is not valid GeoJSON."))
        if area.empty:
            raise ValidationError(_("The area is empty."))
        if area.num_coords > MAX_VERTICES:
            raise ValidationError(
                _("The area has more than %d vertices.") % MAX_VERTICES
            )
        min_x, min_y, max_x, max_y = area.extent
        if min_x < -180 or max_x > 180 or min_y < -MAX_LATITUDE or max_y > MAX_LATITUDE:
            raise ValidationError(
                _("The area must lie within longitude ±180 and latitude ±%s.")
                % MAX_LATITUDE
            )
        # Separately drawn polygons may overlap, so check each and union them.
        for polygon in area if area.geom_type == "MultiPolygon" else [area]:
            if not polygon.valid:
                raise ValidationError(
                    _("The area is not a valid polygon: %s") % polygon.valid_reason
                )
        return area.unary_union

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
