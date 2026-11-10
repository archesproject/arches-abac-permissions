import type {
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
} from "geojson";

export type AreaGeometry =
    | Polygon
    | MultiPolygon
    | Point
    | MultiPoint
    | LineString
    | MultiLineString
    | GeometryCollection;

export type SpatialOperator = "intersects" | "within" | "centroid";

export interface SpatialDefinition {
    graphid: string;
    nodeid: string;
    // EPSG:4326
    geometry: AreaGeometry;
    // Meters; required when the geometry has points or lines.
    buffer?: number;
    // The backend defaults to "intersects".
    operator?: SpatialOperator;
}

export interface ResourceModel {
    graphid: string;
    name: string;
}

export interface GeometryNode {
    nodeid: string;
    name: string;
    alias: string;
}
