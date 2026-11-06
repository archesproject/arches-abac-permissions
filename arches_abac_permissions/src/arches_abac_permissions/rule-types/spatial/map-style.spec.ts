import { describe, expect, it } from "vitest";

import {
    buildStyle,
    layerIdsOf,
} from "@/arches_abac_permissions/rule-types/spatial/map-style.ts";

import type { MapConfig } from "@/arches_abac_permissions/rule-types/spatial/types";

const config: MapConfig = {
    basemaps: [
        {
            name: "streets",
            layers: [{ id: "streets-1", type: "raster", source: "a" }],
            sources: { a: { type: "raster" } },
        },
        {
            name: "satellite",
            layers: [
                { id: "sat-1", type: "raster", source: "b" },
                { id: "sat-orphan", type: "raster", source: "missing" },
            ],
            sources: { b: { type: "raster" } },
        },
    ],
    overlays: [
        {
            name: "parcels",
            layers: [
                {
                    id: "parcels-1",
                    type: "line",
                    source: "c",
                    layout: { "line-cap": "round" },
                },
                { id: "streets-1", type: "line", source: "c" },
            ],
            sources: { c: { type: "vector" } },
        },
    ],
    default_basemap: "streets",
    bounds: null,
    min_zoom: 0,
    max_zoom: 20,
    sprite: "",
    glyphs: "https://example.com/{fontstack}/{range}.pbf",
};

describe("buildStyle", () => {
    const style = buildStyle(config);
    const byId = Object.fromEntries(
        style.layers.map((layer) => [layer.id, layer]),
    );

    it("merges sources and orders basemaps before overlays", () => {
        expect(Object.keys(style.sources)).toEqual(["a", "b", "c"]);
        expect(style.layers.map((layer) => layer.id)).toEqual([
            "streets-1",
            "sat-1",
            "parcels-1",
        ]);
        expect(style.glyphs).toBe(config.glyphs);
        expect("sprite" in style).toBe(false);
    });

    it("shows only the default basemap", () => {
        expect(byId["streets-1"].layout).toBeUndefined();
        expect(byId["sat-1"].layout).toEqual({ visibility: "none" });
    });

    it("hides overlays but keeps their layout", () => {
        expect(byId["parcels-1"].layout).toEqual({
            "line-cap": "round",
            visibility: "none",
        });
    });

    it("hides every basemap when there is no default", () => {
        const hidden = buildStyle({ ...config, default_basemap: null });
        expect(
            hidden.layers.every((layer) => layer.layout?.visibility === "none"),
        ).toBe(true);
    });

    it("handles an empty config", () => {
        const empty = buildStyle({
            ...config,
            basemaps: [],
            overlays: [],
            default_basemap: null,
        });
        expect(empty.layers).toEqual([]);
    });
});

describe("layerIdsOf", () => {
    it("returns the layer ids owned by a map layer", () => {
        expect(layerIdsOf(config, "satellite")).toEqual(["sat-1"]);
        expect(layerIdsOf(config, "parcels")).toEqual(["parcels-1"]);
        expect(layerIdsOf(config, "streets")).toEqual(["streets-1"]);
        expect(layerIdsOf(config, "nope")).toEqual([]);
    });
});
