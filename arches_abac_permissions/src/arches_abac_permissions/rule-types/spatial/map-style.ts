import type { StyleSpecification } from "maplibre-gl";

import type {
    MapConfig,
    MapLayerConfig,
} from "@/arches_abac_permissions/rule-types/spatial/types";

type Definition = Record<string, unknown>;

// Maps each layer id to the name of the MapLayerConfig it belongs to.
function layerOwners(config: MapConfig): Map<string, string> {
    const owners = new Map<string, string>();
    for (const entry of [...config.basemaps, ...config.overlays]) {
        for (const definition of validLayers(entry)) {
            const id = definition.id as string;
            if (!owners.has(id)) {
                owners.set(id, entry.name);
            }
        }
    }
    return owners;
}

// Layers without their source are dropped; one would stop the style loading.
function validLayers(entry: MapLayerConfig): Definition[] {
    return entry.layers.filter(
        (layer) =>
            typeof layer.id === "string" &&
            (!layer.source || (layer.source as string) in entry.sources),
    );
}

export function layerIdsOf(config: MapConfig, name: string): string[] {
    return [...layerOwners(config)]
        .filter(([, owner]) => owner === name)
        .map(([id]) => id);
}

// One style holding every basemap then every overlay. Only the default
// basemap starts visible; toggling is done through layer visibility.
export function buildStyle(config: MapConfig): StyleSpecification {
    const sources: Record<string, Record<string, unknown>> = {};
    const layers: Definition[] = [];
    const seen = new Set<string>();
    const visibleName = config.default_basemap;
    const basemapNames = new Set(config.basemaps.map((entry) => entry.name));
    for (const entry of [...config.basemaps, ...config.overlays]) {
        Object.assign(sources, entry.sources);
        const isHidden =
            !basemapNames.has(entry.name) ||
            config.overlays.includes(entry) ||
            entry.name !== visibleName;
        for (const definition of validLayers(entry)) {
            const id = definition.id as string;
            if (seen.has(id)) {
                continue;
            }
            seen.add(id);
            layers.push(
                isHidden
                    ? {
                          ...definition,
                          layout: {
                              ...(definition.layout as Definition | undefined),
                              visibility: "none",
                          },
                      }
                    : definition,
            );
        }
    }
    return {
        version: 8,
        ...(config.sprite ? { sprite: config.sprite } : {}),
        ...(config.glyphs ? { glyphs: config.glyphs } : {}),
        sources,
        layers,
    } as StyleSpecification;
}
