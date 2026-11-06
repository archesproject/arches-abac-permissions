import type { MultiPolygon, Polygon } from "geojson";

export type AreaGeometry = Polygon | MultiPolygon;

export type SpatialOperator = "intersects" | "within" | "centroid";

export interface SpatialDefinition {
    graphid: string;
    nodeid: string;
    // EPSG:4326
    geometry: AreaGeometry;
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

export interface Basemap {
    layers: Record<string, unknown>[];
    sources: Record<string, Record<string, unknown>>;
}

export interface MapConfig {
    basemap: Basemap | null;
    // [west, south, east, north]
    bounds: [number, number, number, number] | null;
    min_zoom: number;
    max_zoom: number;
    sprite: string;
    glyphs: string;
}
