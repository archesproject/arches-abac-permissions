import type { Feature, FeatureCollection, Geometry, Polygon } from "geojson";

import type { AreaGeometry } from "@/arches_abac_permissions/rule-types/spatial/types";

const POLYGONAL_TYPES = ["Polygon", "MultiPolygon"];
const SIMPLE_TYPES = [
    ...POLYGONAL_TYPES,
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
];

// Flattens Multi* geometries and collections into simple geometries.
export function partsOf(geometry: Geometry | undefined): Geometry[] {
    if (!geometry) {
        return [];
    }
    switch (geometry.type) {
        case "GeometryCollection":
            return geometry.geometries.flatMap(partsOf);
        case "MultiPolygon":
            return geometry.coordinates.map((coordinates) => ({
                type: "Polygon",
                coordinates,
            }));
        case "MultiPoint":
            return geometry.coordinates.map((coordinates) => ({
                type: "Point",
                coordinates,
            }));
        case "MultiLineString":
            return geometry.coordinates.map((coordinates) => ({
                type: "LineString",
                coordinates,
            }));
        default:
            return [geometry];
    }
}

// Combines geometries into the rule's area; undefined when there are none.
export function areaOf(geometries: Geometry[]): AreaGeometry | undefined {
    const parts = geometries.flatMap(partsOf);
    if (!parts.length) {
        return undefined;
    }
    if (parts.every((part) => POLYGONAL_TYPES.includes(part.type))) {
        const rings = parts.map((part) => (part as Polygon).coordinates);
        return rings.length === 1
            ? { type: "Polygon", coordinates: rings[0] }
            : { type: "MultiPolygon", coordinates: rings };
    }
    return { type: "GeometryCollection", geometries: parts };
}

export function toFeatureCollection(
    area: AreaGeometry | undefined,
): FeatureCollection {
    return {
        type: "FeatureCollection",
        features: partsOf(area).map((geometry) => ({
            type: "Feature",
            properties: {},
            geometry,
        })),
    };
}

// Points and lines have no area until buffered.
export function needsBuffer(area: AreaGeometry | undefined): boolean {
    return partsOf(area).some((part) => !POLYGONAL_TYPES.includes(part.type));
}

// Accepts a geometry, Feature, FeatureCollection or GeometryCollection of
// polygons, points and lines. Throws on anything else.
export function parseArea(text: string): AreaGeometry {
    const parsed = JSON.parse(text);
    const geometries: unknown[] =
        parsed?.type === "FeatureCollection"
            ? (parsed.features ?? []).map(
                  (feature: Feature) => feature?.geometry,
              )
            : [parsed?.type === "Feature" ? parsed.geometry : parsed];
    const valid = geometries.every((geometry) => isSimple(geometry, true));
    const area = valid ? areaOf(geometries as Geometry[]) : undefined;
    if (!area) {
        throw new Error("Not a supported geometry");
    }
    return area;
}

function isSimple(geometry: unknown, allowCollection: boolean): boolean {
    const candidate = geometry as Geometry | null;
    if (candidate?.type === "GeometryCollection" && allowCollection) {
        return (
            Array.isArray(candidate.geometries) &&
            candidate.geometries.every((member) => isSimple(member, false))
        );
    }
    return (
        SIMPLE_TYPES.includes(candidate?.type ?? "") &&
        Array.isArray((candidate as { coordinates?: unknown }).coordinates)
    );
}
