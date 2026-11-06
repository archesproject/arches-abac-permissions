import { describe, expect, it } from "vitest";

import {
    areaOf,
    parseArea,
    needsBuffer,
    partsOf,
    positionsOf,
    toFeatureCollection,
} from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";

import type { LineString, Point, Polygon } from "geojson";

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

const point: Point = { type: "Point", coordinates: [2, 3] };
const line: LineString = {
    type: "LineString",
    coordinates: [
        [0, 0],
        [1, 1],
    ],
};

describe("geometry helpers", () => {
    it("splits an area into simple geometries", () => {
        expect(partsOf(undefined)).toEqual([]);
        expect(partsOf(square)).toEqual([square]);
        expect(
            partsOf({
                type: "MultiPolygon",
                coordinates: [square.coordinates, other.coordinates],
            }),
        ).toEqual([square, other]);
        expect(
            partsOf({
                type: "GeometryCollection",
                geometries: [
                    {
                        type: "MultiPoint",
                        coordinates: [
                            [0, 0],
                            [1, 1],
                        ],
                    },
                    {
                        type: "MultiLineString",
                        coordinates: [line.coordinates],
                    },
                ],
            }),
        ).toEqual([
            { type: "Point", coordinates: [0, 0] },
            { type: "Point", coordinates: [1, 1] },
            line,
        ]);
    });

    it("combines geometries into an area", () => {
        expect(areaOf([])).toBeUndefined();
        expect(areaOf([square])).toEqual(square);
        expect(areaOf([square, other])).toEqual({
            type: "MultiPolygon",
            coordinates: [square.coordinates, other.coordinates],
        });
        expect(areaOf([point])).toEqual({
            type: "GeometryCollection",
            geometries: [point],
        });
        expect(areaOf([square, line, point])).toEqual({
            type: "GeometryCollection",
            geometries: [square, line, point],
        });
    });

    it("builds a feature collection with a feature per part", () => {
        expect(toFeatureCollection(undefined).features).toEqual([]);
        expect(toFeatureCollection(areaOf([square, point]))).toEqual({
            type: "FeatureCollection",
            features: [
                { type: "Feature", properties: {}, geometry: square },
                { type: "Feature", properties: {}, geometry: point },
            ],
        });
    });

    it("tells whether an area needs a buffer", () => {
        expect(needsBuffer(undefined)).toBe(false);
        expect(needsBuffer(square)).toBe(false);
        expect(needsBuffer(point)).toBe(true);
        expect(needsBuffer(areaOf([square, line]))).toBe(true);
    });

    it("lists the positions of an area", () => {
        expect(positionsOf(undefined)).toEqual([]);
        expect(positionsOf(point)).toEqual([[2, 3]]);
        expect(positionsOf(line)).toEqual(line.coordinates);
        expect(positionsOf(square)).toEqual(square.coordinates[0]);
    });

    it("parses geometries, features and feature collections", () => {
        expect(parseArea(JSON.stringify(square))).toEqual(square);
        expect(parseArea(JSON.stringify(point))).toEqual({
            type: "GeometryCollection",
            geometries: [point],
        });
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
        expect(
            parseArea(
                JSON.stringify({
                    type: "FeatureCollection",
                    features: [
                        { type: "Feature", properties: {}, geometry: line },
                        { type: "Feature", properties: {}, geometry: point },
                    ],
                }),
            ),
        ).toEqual({ type: "GeometryCollection", geometries: [line, point] });
        expect(
            parseArea(
                JSON.stringify({
                    type: "GeometryCollection",
                    geometries: [square, point],
                }),
            ),
        ).toEqual({ type: "GeometryCollection", geometries: [square, point] });
    });

    it("rejects unsupported or empty input", () => {
        expect(() => parseArea("not json")).toThrow();
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
        expect(() =>
            parseArea(
                JSON.stringify({
                    type: "GeometryCollection",
                    geometries: [
                        { type: "GeometryCollection", geometries: [point] },
                    ],
                }),
            ),
        ).toThrow();
        expect(() =>
            parseArea(JSON.stringify({ type: "Circle", coordinates: [0, 0] })),
        ).toThrow();
    });
});
