import { describe, expect, it } from "vitest";

import {
    areaOf,
    parseArea,
    polygonsOf,
} from "@/arches_abac_permissions/geometry.ts";

import type { Polygon } from "geojson";

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
const other: Polygon = {
    type: "Polygon",
    coordinates: [
        [
            [5, 5],
            [6, 5],
            [6, 6],
            [5, 5],
        ],
    ],
};

describe("geometry helpers", () => {
    it("splits an area into polygons", () => {
        expect(polygonsOf(undefined)).toEqual([]);
        expect(polygonsOf(square)).toEqual([square]);
        expect(
            polygonsOf({
                type: "MultiPolygon",
                coordinates: [square.coordinates, other.coordinates],
            }),
        ).toEqual([square, other]);
    });

    it("combines polygons into an area", () => {
        expect(areaOf([])).toBeUndefined();
        expect(
            areaOf([{ type: "Point", coordinates: [0, 0] }]),
        ).toBeUndefined();
        expect(areaOf([square])).toEqual(square);
        expect(areaOf([square, other])).toEqual({
            type: "MultiPolygon",
            coordinates: [square.coordinates, other.coordinates],
        });
    });

    it("parses geometries, features and feature collections", () => {
        expect(parseArea(JSON.stringify(square))).toEqual(square);
        expect(
            parseArea(
                JSON.stringify({
                    type: "Feature",
                    properties: {},
                    geometry: square,
                }),
            ),
        ).toEqual(square);
        expect(
            parseArea(
                JSON.stringify({
                    type: "FeatureCollection",
                    features: [
                        { type: "Feature", properties: {}, geometry: square },
                        { type: "Feature", properties: {}, geometry: other },
                    ],
                }),
            ).type,
        ).toBe("MultiPolygon");
    });

    it("rejects anything that isn't polygons", () => {
        expect(() => parseArea("not json")).toThrow();
        expect(() =>
            parseArea(JSON.stringify({ type: "Point", coordinates: [0, 0] })),
        ).toThrow();
        expect(() =>
            parseArea(
                JSON.stringify({ type: "FeatureCollection", features: [] }),
            ),
        ).toThrow();
        expect(() =>
            parseArea(
                JSON.stringify({
                    type: "FeatureCollection",
                    features: [
                        { type: "Feature", geometry: square },
                        { type: "Feature", geometry: null },
                    ],
                }),
            ),
        ).toThrow();
    });
});
