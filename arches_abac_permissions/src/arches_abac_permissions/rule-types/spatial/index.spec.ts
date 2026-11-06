import { describe, expect, it } from "vitest";

import spatial from "@/arches_abac_permissions/rule-types/spatial/index.ts";

import type { Point, Polygon } from "geojson";

const square: Polygon = {
    type: "Polygon",
    coordinates: [
        [
            [0, 0],
            [1, 0],
            [1, 1],
            [0, 0],
        ],
    ],
};
const point: Point = { type: "Point", coordinates: [0, 0] };

describe("spatial rule completeness", () => {
    const base = { graphid: "g", nodeid: "n" };

    it("requires a model, node and geometry", () => {
        expect(spatial.isComplete({})).toBe(false);
        expect(spatial.isComplete({ graphid: "g", geometry: square })).toBe(
            false,
        );
        expect(spatial.isComplete({ ...base })).toBe(false);
        expect(spatial.isComplete({ ...base, geometry: square })).toBe(true);
    });

    it("requires a buffer for points and lines", () => {
        const geometry = {
            type: "GeometryCollection",
            geometries: [point],
        } as const;
        expect(spatial.isComplete({ ...base, geometry })).toBe(false);
        expect(spatial.isComplete({ ...base, geometry, buffer: 0 })).toBe(
            false,
        );
        expect(spatial.isComplete({ ...base, geometry, buffer: 10 })).toBe(
            true,
        );
    });
});
