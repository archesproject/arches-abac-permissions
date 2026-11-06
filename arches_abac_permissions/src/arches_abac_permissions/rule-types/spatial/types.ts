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

export interface MapLayerConfig {
    name: string;
    layers: Record<string, unknown>[];
    sources: Record<string, Record<string, unknown>>;
}

export interface MapConfig {
    basemaps: MapLayerConfig[];
    overlays: MapLayerConfig[];
    default_basemap: string | null;
    // [west, south, east, north]
    bounds: [number, number, number, number] | null;
    min_zoom: number;
    max_zoom: number;
    sprite: string;
    glyphs: string;
}
