import json
import math
import uuid
from functools import lru_cache

from django.contrib.gis.db.models.functions import Centroid
from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry
from django.db import connection
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from arches.app.models.models import (
    GeoJSONGeometry,
    ResourceInstance,
)
from arches_abac_permissions.models import InclusionRule
from arches_abac_permissions.rules.utils import get_resource_node
from arches_abac_permissions.rule_types import RuleType

GEOMETRY_DATATYPE = "geojson-feature-collection"
POLYGONAL_TYPES = ("Polygon", "MultiPolygon")
SIMPLE_TYPES = POLYGONAL_TYPES + (
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
)
COLLECTION = "GeometryCollection"
MAX_BUFFER = 100000  # meters
MAX_VERTICES = 10000
# Geometries are stored in EPSG:3857, which is undefined beyond this latitude.
MAX_LATITUDE = 85.05112878
# Wider areas are likely meant to cross the antimeridian, which isn't supported.
MAX_LONGITUDE_SPAN = 180
INTERSECTS = "intersects"
WITHIN = "within"
CENTROID = "centroid"
OPERATORS = (INTERSECTS, WITHIN, CENTROID)


class SpatialRule(InclusionRule):
    """
    Rule matching resources by where their geometry node lies relative to an
    area.

    definition: {
        "graphid": "<graph id>",
        "nodeid": "<geojson-feature-collection node id>",
        "geometry": <GeoJSON Polygon, Point, LineString, their Multi*
                     variants or a flat GeometryCollection, in EPSG:4326>,
        "buffer": <meters, optional; required for points and lines>,
        "operator": "intersects" (default) | "within" | "centroid"
    }

    Evaluated against the geojson_geometries table, so arches-search isn't
    required.
    """

    rule_type = RuleType(
        key="spatial",
        label=gettext_lazy("Resource is in Area"),
        description=gettext_lazy(
            "Matches resources by where their geometry lies relative to an area"
        ),
        icon="pi pi-map",
        definition_keys=("graphid", "nodeid", "geometry", "buffer", "operator"),
    )

    @classmethod
    def clean_definition(cls, raw_definition, definition_keys):
        definition = super().clean_definition(
            raw_definition,
            [key for key in definition_keys if key not in ("geometry", "buffer")],
        )
        definition.setdefault("operator", INTERSECTS)
        geometry = raw_definition.get("geometry")
        if isinstance(geometry, dict):
            # Drop other members (e.g. "crs"); they're ignored anyway.
            geometry = strip_geometry(geometry)
        if geometry is not None:
            definition["geometry"] = geometry
        if raw_definition.get("buffer") is not None:
            definition["buffer"] = raw_definition["buffer"]
        return definition

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        _graph_id, node_id, area, operator = cls.get_args(inclusion_rule.definition)
        return ResourceInstance.objects.filter(
            pk__in=cls.matching_geometries(node_id, area, operator).values(
                "resourceinstance_id"
            )
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        graph_id, node_id, area, operator = cls.get_args(inclusion_rule.definition)
        if resource.graph_id != graph_id:
            return False
        return (
            cls.matching_geometries(node_id, area, operator)
            .filter(resourceinstance=resource)
            .exists()
        )

    @staticmethod
    def matching_geometries(node_id, area, operator):
        """
        Return the node's geometries whose resources match. Each operator
        prefilters with a lookup the GiST index can use.
        """
        if operator == CENTROID:
            # A centroid can lie outside its geometry, but never outside its
            # bounding box.
            return (
                GeoJSONGeometry.objects.filter(node_id=node_id, geom__bboverlaps=area)
                .annotate(centroid=Centroid("geom"))
                .filter(centroid__intersects=area)
            )
        geometries = GeoJSONGeometry.objects.filter(
            node_id=node_id, geom__intersects=area
        )
        if operator == WITHIN:
            # Every geometry of the resource in the node must be in the area.
            outside = GeoJSONGeometry.objects.filter(
                node_id=node_id,
                resourceinstance_id__in=geometries.values("resourceinstance_id"),
            ).exclude(geom__within=area)
            return geometries.exclude(
                resourceinstance_id__in=outside.values("resourceinstance_id")
            )
        return geometries

    @classmethod
    def validate_definition(cls, inclusion_rule):
        cls.parse_definition(inclusion_rule.definition)

    @classmethod
    def get_index_sql(cls, inclusion_rule):
        node, _area, _operator = cls.parse_definition(inclusion_rule.definition)
        # Ids come from the database, so formatting them into SQL is safe.
        return (
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS abac_geom_node_{node.pk.hex}\n"
            f"    ON geojson_geometries USING gist (geom)\n"
            f"    WHERE nodeid = '{node.pk}';"
        )

    @classmethod
    def get_args(cls, definition):
        """Return the graph id, node id, area and operator without database access."""
        graphid = definition.get("graphid")
        nodeid = definition.get("nodeid")
        geometry = definition.get("geometry")
        operator = definition.get("operator", INTERSECTS)
        if not graphid or not nodeid or not geometry:
            raise ValidationError(
                _("Spatial rules require a 'graphid', a 'nodeid' and a 'geometry'.")
            )
        if operator not in OPERATORS:
            raise ValidationError(
                _("The operator must be one of %s.") % ", ".join(OPERATORS)
            )
        try:
            graph_id = uuid.UUID(str(graphid))
        except ValueError:
            raise ValidationError(_("%s is not the id of a resource model.") % graphid)
        try:
            node_id = uuid.UUID(str(nodeid))
        except ValueError:
            raise ValidationError(
                _("%(nodeid)s is not the id of a node of graph %(graphid)s.")
                % {"nodeid": nodeid, "graphid": graphid}
            )
        area = cls.parse_geometry(geometry, definition.get("buffer"))
        return graph_id, node_id, area, operator

    @classmethod
    def parse_definition(cls, definition):
        """Return the DB-validated geometry node, the area and the operator."""
        graph_id, node_id, area, operator = cls.get_args(definition)
        node = get_resource_node(graph_id, node_id)
        if node.datatype != GEOMETRY_DATATYPE:
            raise ValidationError(_("The node must be a geometry node."))
        return node, area, operator

    @staticmethod
    def parse_geometry(geometry, buffer=None):
        """Return the area for a geometry and optional buffer in meters."""
        if not isinstance(geometry, dict):
            raise ValidationError(_("The area must be a GeoJSON geometry."))
        geometry_type = geometry.get("type")
        if geometry_type == COLLECTION:
            members = geometry.get("geometries")
            if not isinstance(members, list) or not all(
                isinstance(member, dict) and member.get("type") in SIMPLE_TYPES
                for member in members
            ):
                raise ValidationError(
                    _("A geometry collection can only hold simple geometries.")
                )
        elif geometry_type not in SIMPLE_TYPES:
            raise ValidationError(
                _("The area must be a Polygon, Point, LineString or a collection.")
            )
        buffer = validate_buffer(buffer)
        # Only type, coordinates and geometries are read, so a "crs" member
        # can't reinterpret the coordinates.
        try:
            canonical = json.dumps(strip_geometry(geometry), sort_keys=True)
        except (ValueError, TypeError):
            raise ValidationError(_("The area is not valid GeoJSON."))
        # Copied so callers can't change the cached area.
        return parse_area(canonical, buffer).clone()

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"


def strip_geometry(geometry):
    """Keep only the members that are read; other values pass through."""
    if not isinstance(geometry, dict):
        return geometry
    if geometry.get("type") == COLLECTION:
        members = geometry.get("geometries")
        return {
            "type": COLLECTION,
            "geometries": (
                [strip_geometry(member) for member in members]
                if isinstance(members, list)
                else members
            ),
        }
    return {"type": geometry.get("type"), "coordinates": geometry.get("coordinates")}


def validate_buffer(buffer):
    if buffer is None:
        return 0
    if (
        isinstance(buffer, bool)
        or not isinstance(buffer, (int, float))
        or not math.isfinite(buffer)
        or not 0 <= buffer <= MAX_BUFFER
    ):
        raise ValidationError(
            _("The buffer must be a number of meters from 0 to %d.") % MAX_BUFFER
        )
    return float(buffer)


def simple_parts(geometry):
    """Flatten Multi* geometries and collections into simple geometries."""
    if geometry.geom_type.startswith("Multi") or geometry.geom_type == COLLECTION:
        return [part for member in geometry for part in simple_parts(member)]
    return [geometry]


def check_bounds(area):
    if area.empty:
        raise ValidationError(_("The area is empty."))
    if area.num_coords > MAX_VERTICES:
        raise ValidationError(_("The area has more than %d vertices.") % MAX_VERTICES)
    min_x, min_y, max_x, max_y = area.extent
    if min_x < -180 or max_x > 180 or min_y < -MAX_LATITUDE or max_y > MAX_LATITUDE:
        raise ValidationError(
            _("The area must lie within longitude ±180 and latitude ±%s.")
            % MAX_LATITUDE
        )
    if max_x - min_x > MAX_LONGITUDE_SPAN:
        raise ValidationError(
            _(
                "The area can't be more than %d degrees of longitude wide or "
                "cross the antimeridian."
            )
            % MAX_LONGITUDE_SPAN
        )


def buffer_parts(parts, buffer):
    """Buffer by meters using PostGIS geography, merged in one query."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_AsEWKB(ST_Union(ST_Buffer(ST_GeomFromEWKB(g)::geography, %s)::geometry))"
            " FROM unnest(%s::bytea[]) AS g",
            (buffer, [bytes(part.ewkb) for part in parts]),
        )
        area = GEOSGeometry(memoryview(cursor.fetchone()[0]))
    area.srid = 4326
    return area


@lru_cache(maxsize=256)
def parse_area(canonical_geojson, buffer=0):
    """
    Validate, buffer and union an area. Cached since every permission check
    of a rule parses the same area.
    """
    try:
        area = GEOSGeometry(canonical_geojson, srid=4326)
    except (GEOSException, GDALException, ValueError, TypeError):
        raise ValidationError(_("The area is not valid GeoJSON."))
    check_bounds(area)
    parts = simple_parts(area)
    # Separately drawn polygons may overlap, so check each and union them.
    for part in parts:
        if part.geom_type == "Polygon" and not part.valid:
            raise ValidationError(
                _("The area is not a valid polygon: %s") % part.valid_reason
            )
    if buffer > 0:
        area = buffer_parts(parts, buffer).unary_union
        area.srid = 4326
        check_bounds(area)
        return area
    if any(part.geom_type not in POLYGONAL_TYPES for part in parts):
        raise ValidationError(_("Points and lines need a buffer greater than 0."))
    return area.unary_union
