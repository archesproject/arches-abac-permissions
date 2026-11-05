import json
from functools import lru_cache

from django.contrib.gis.db.models.functions import Centroid
from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from arches.app.models.models import (
    GeoJSONGeometry,
    GraphModel,
    Node,
    ResourceInstance,
)
from arches_abac_permissions.models import InclusionRule
from arches_abac_permissions.rule_types import RuleType

GEOMETRY_DATATYPE = "geojson-feature-collection"
GEOMETRY_TYPES = ("Polygon", "MultiPolygon")
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
        "geometry": <GeoJSON Polygon or MultiPolygon in EPSG:4326>,
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
        definition_keys=("graphid", "nodeid", "geometry", "operator"),
    )

    @classmethod
    def clean_definition(cls, raw_definition, definition_keys):
        definition = super().clean_definition(
            raw_definition, [key for key in definition_keys if key != "geometry"]
        )
        definition.setdefault("operator", INTERSECTS)
        geometry = raw_definition.get("geometry")
        if isinstance(geometry, dict):
            # Drop other members (e.g. "crs"); they're ignored anyway.
            geometry = {
                "type": geometry.get("type"),
                "coordinates": geometry.get("coordinates"),
            }
        if geometry is not None:
            definition["geometry"] = geometry
        return definition

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        node, area, operator = cls.parse_definition(inclusion_rule.definition)
        return ResourceInstance.objects.filter(
            pk__in=cls.matching_geometries(node, area, operator).values(
                "resourceinstance_id"
            )
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        node, area, operator = cls.parse_definition(inclusion_rule.definition)
        if resource.graph_id != node.graph_id:
            return False
        return (
            cls.matching_geometries(node, area, operator)
            .filter(resourceinstance=resource)
            .exists()
        )

    @staticmethod
    def matching_geometries(node, area, operator):
        """
        Return the node's geometries whose resources match. Each operator
        prefilters with a lookup the GiST index can use.
        """
        if operator == CENTROID:
            # A centroid can lie outside its geometry, but never outside its
            # bounding box.
            return (
                GeoJSONGeometry.objects.filter(node=node, geom__bboverlaps=area)
                .annotate(centroid=Centroid("geom"))
                .filter(centroid__intersects=area)
            )
        geometries = GeoJSONGeometry.objects.filter(node=node, geom__intersects=area)
        if operator == WITHIN:
            # Every geometry of the resource in the node must be in the area.
            outside = GeoJSONGeometry.objects.filter(
                node=node,
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
    def parse_definition(cls, definition):
        """Return the geometry node, the area as a GEOSGeometry and the operator."""
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
            # Draft graphs (source_identifier set) are replaced when published.
            node = Node.objects.get(
                pk=nodeid,
                graph_id=graphid,
                graph__isresource=True,
                graph__source_identifier=None,
            )
        except (Node.DoesNotExist, ValidationError):
            node = None
        if node is None:
            try:
                is_graph = GraphModel.objects.filter(
                    pk=graphid, isresource=True, source_identifier=None
                ).exists()
            except ValidationError:
                is_graph = False
            if not is_graph:
                raise ValidationError(
                    _("%s is not the id of a resource model.") % graphid
                )
            raise ValidationError(
                _("%(nodeid)s is not the id of a node of graph %(graphid)s.")
                % {"nodeid": nodeid, "graphid": graphid}
            )
        if node.datatype != GEOMETRY_DATATYPE:
            raise ValidationError(_("The node must be a geometry node."))
        return node, cls.parse_geometry(geometry), operator

    @staticmethod
    def parse_geometry(geometry):
        if not isinstance(geometry, dict) or geometry.get("type") not in GEOMETRY_TYPES:
            raise ValidationError(_("The area must be a Polygon or MultiPolygon."))
        # Only type and coordinates are read, so a "crs" member can't
        # reinterpret the coordinates.
        try:
            canonical = json.dumps(
                {"type": geometry["type"], "coordinates": geometry.get("coordinates")},
                sort_keys=True,
            )
        except (ValueError, TypeError):
            raise ValidationError(_("The area is not valid GeoJSON."))
        # Copied so callers can't change the cached area.
        return parse_area(canonical).clone()

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"


@lru_cache(maxsize=256)
def parse_area(canonical_geojson):
    """
    Validate and union an area. Cached since every permission check of a
    rule parses the same area.
    """
    try:
        area = GEOSGeometry(canonical_geojson, srid=4326)
    except (GEOSException, GDALException, ValueError, TypeError):
        raise ValidationError(_("The area is not valid GeoJSON."))
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
    # Separately drawn polygons may overlap, so check each and union them.
    for polygon in area if area.geom_type == "MultiPolygon" else [area]:
        if not polygon.valid:
            raise ValidationError(
                _("The area is not a valid polygon: %s") % polygon.valid_reason
            )
    return area.unary_union
