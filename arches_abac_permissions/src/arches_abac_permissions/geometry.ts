import type { Feature, Geometry, Polygon, Position } from "geojson";

import type { AreaGeometry } from "@/arches_abac_permissions/types";

export function polygonsOf(geometry: AreaGeometry | undefined): Polygon[] {
    if (!geometry) {
        return [];
    }
    if (geometry.type === "Polygon") {
        return [geometry];
    }
    return geometry.coordinates.map((coordinates) => ({
        type: "Polygon",
        coordinates,
    }));
}

// Combines polygons into the rule's area; undefined when there are none.
export function areaOf(geometries: Geometry[]): AreaGeometry | undefined {
    const rings: Position[][][] = geometries.flatMap((geometry) => {
        if (geometry.type === "Polygon") {
            return [geometry.coordinates];
        }
        if (geometry.type === "MultiPolygon") {
            return geometry.coordinates;
        }
        return [];
    });
    if (!rings.length) {
        return undefined;
    }
    return rings.length === 1
        ? { type: "Polygon", coordinates: rings[0] }
        : { type: "MultiPolygon", coordinates: rings };
}

// Accepts a Polygon or MultiPolygon geometry, Feature or FeatureCollection.
// Throws when the text holds no polygons or anything else.
export function parseArea(text: string): AreaGeometry {
    const parsed = JSON.parse(text);
    const geometries: unknown[] =
        parsed?.type === "FeatureCollection"
            ? (parsed.features ?? []).map(
                  (feature: Feature) => feature?.geometry,
              )
            : [parsed?.type === "Feature" ? parsed.geometry : parsed];
    const valid = geometries.every(
        (geometry) =>
            isPolygonal(geometry) &&
            Array.isArray((geometry as Polygon).coordinates),
    );
    const area = valid ? areaOf(geometries as Geometry[]) : undefined;
    if (!area) {
        throw new Error("Not a polygon");
    }
    return area;
}

function isPolygonal(geometry: unknown): boolean {
    const type = (geometry as Geometry | null)?.type;
    return type === "Polygon" || type === "MultiPolygon";
}
