<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import MapboxDraw from "@mapbox/mapbox-gl-draw";
import {
    Map as MapLibreMap,
    NavigationControl,
    setWorkerUrl,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import Button from "openvue/button";
import Select from "openvue/select";

import {
    areaOf,
    polygonsOf,
} from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";

import type { Feature, FeatureCollection, Polygon, Position } from "geojson";
import type {
    IControl,
    LayerSpecification,
    LngLatBoundsLike,
    StyleSpecification,
} from "maplibre-gl";
import type {
    AreaGeometry,
    MapConfig,
} from "@/arches_abac_permissions/rule-types/spatial/types";

// The subset of mapbox-gl-draw used here; the package ships no types.
interface DrawControl extends IControl {
    set(collection: FeatureCollection): void;
    getAll(): FeatureCollection;
    changeMode(mode: string): void;
    trash(): void;
    deleteAll(): void;
}

// Serve the worker as a webpack-emitted asset, as arches core does.
setWorkerUrl(
    new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).href,
);
new URL("maplibre-gl/dist/maplibre-gl-shared.mjs?asset", import.meta.url);

const DRAW_POLYGON = "draw_polygon";
const SIMPLE_SELECT = "simple_select";

const props = defineProps<{ config: MapConfig; describedBy?: string }>();
const area = defineModel<AreaGeometry | undefined>({ required: true });

const { $gettext, $ngettext } = useGettext();

const container = ref<HTMLElement>();
const basemapId = ref(
    (
        props.config.basemaps.find((basemap) => basemap.is_default) ??
        props.config.basemaps[0]
    )?.id,
);
const isDrawing = ref(false);
const hasSelection = ref(false);

let map: MapLibreMap | null = null;
let draw: DrawControl | null = null;
// The area last read from the map, to tell our own updates from outside ones.
let syncedArea = "";
let isLoaded = false;

const polygonCount = computed(() => polygonsOf(area.value).length);
const status = computed(() =>
    polygonCount.value
        ? $ngettext(
              "The area has %{count} polygon.",
              "The area has %{count} polygons.",
              polygonCount.value,
              { count: String(polygonCount.value) },
          )
        : $gettext("No area has been drawn."),
);

watch(area, (geometry) => {
    if (JSON.stringify(geometry ?? null) !== syncedArea) {
        showArea(geometry, true);
    }
});

watch(basemapId, (selected) => {
    if (!map) {
        return;
    }
    for (const basemap of props.config.basemaps) {
        for (const layer of basemap.layers) {
            const id = layerId(basemap.id, layer.id);
            if (map.getLayer(id)) {
                map.setLayoutProperty(
                    id,
                    "visibility",
                    basemap.id === selected ? "visible" : "none",
                );
            }
        }
    }
});

onMounted(() => {
    const bounds = boundsOf(area.value) ?? props.config.bounds ?? undefined;
    map = new MapLibreMap({
        container: container.value!,
        style: buildStyle(),
        bounds,
        fitBoundsOptions: { padding: 40, maxZoom: 16 },
        minZoom: props.config.min_zoom,
        maxZoom: props.config.max_zoom,
        attributionControl: { compact: true },
    });
    map.getCanvas().setAttribute("aria-label", $gettext("Area map"));
    if (props.describedBy) {
        map.getCanvas().setAttribute("aria-describedby", props.describedBy);
    }
    map.addControl(new NavigationControl({ showCompass: false }));
    draw = new MapboxDraw({
        displayControlsDefault: false,
        defaultMode: SIMPLE_SELECT,
    }) as DrawControl;
    map.addControl(draw);
    map.on("load", () => {
        isLoaded = true;
        showArea(area.value, false);
    });
    onDraw("draw.create", readArea);
    onDraw("draw.update", readArea);
    onDraw("draw.delete", readArea);
    onDraw<{ mode: string }>("draw.modechange", (event) => {
        isDrawing.value = event.mode === DRAW_POLYGON;
    });
    onDraw<{ features: Feature[] }>("draw.selectionchange", (event) => {
        hasSelection.value = event.features.length > 0;
    });
});

onBeforeUnmount(() => {
    map?.remove();
    map = null;
    draw = null;
    isLoaded = false;
});

function layerId(basemapIdValue: string, id: unknown): string {
    return `${basemapIdValue}/${id}`;
}

function buildStyle(): StyleSpecification {
    const sources = Object.assign(
        {},
        ...props.config.basemaps.map((basemap) => basemap.sources),
    );
    const layers = props.config.basemaps.flatMap((basemap) =>
        basemap.layers.map((layer) => ({
            ...layer,
            id: layerId(basemap.id, layer.id),
            layout: {
                ...(layer.layout as object | undefined),
                visibility: basemap.id === basemapId.value ? "visible" : "none",
            },
        })),
    );
    return {
        version: 8,
        ...(props.config.sprite ? { sprite: props.config.sprite } : {}),
        ...(props.config.glyphs ? { glyphs: props.config.glyphs } : {}),
        sources,
        layers: layers as LayerSpecification[],
    } as StyleSpecification;
}

function boundsOf(geometry: AreaGeometry | undefined): LngLatBoundsLike | null {
    const positions: Position[] = polygonsOf(geometry).flatMap(
        (polygon) => polygon.coordinates.flat() as Position[],
    );
    if (!positions.length) {
        return null;
    }
    const xs = positions.map((position) => position[0]);
    const ys = positions.map((position) => position[1]);
    return [
        [Math.min(...xs), Math.min(...ys)],
        [Math.max(...xs), Math.max(...ys)],
    ];
}

function showArea(geometry: AreaGeometry | undefined, fit: boolean): void {
    syncedArea = JSON.stringify(geometry ?? null);
    if (!draw || !isLoaded) {
        return;
    }
    const features: Feature<Polygon>[] = polygonsOf(geometry).map(
        (polygon) => ({ type: "Feature", properties: {}, geometry: polygon }),
    );
    draw.set({ type: "FeatureCollection", features });
    hasSelection.value = false;
    const bounds = boundsOf(geometry);
    if (fit && bounds && map) {
        map.fitBounds(bounds, { padding: 40, maxZoom: 16, duration: 0 });
    }
}

function readArea(): void {
    if (!draw) {
        return;
    }
    const geometries = draw
        .getAll()
        .features.map((feature) => feature.geometry);
    const next = areaOf(geometries);
    syncedArea = JSON.stringify(next ?? null);
    area.value = next;
}

function startDrawing(): void {
    draw?.changeMode(isDrawing.value ? SIMPLE_SELECT : DRAW_POLYGON);
    isDrawing.value = !isDrawing.value;
}

function deleteSelected(): void {
    draw?.trash();
    readArea();
}

function clearArea(): void {
    draw?.deleteAll();
    isDrawing.value = false;
    readArea();
}

// Draw events aren't part of maplibre's typed event map.
function onDraw<T>(type: string, listener: (event: T) => void): void {
    (
        map as unknown as {
            on: (type: string, listener: (event: T) => void) => void;
        }
    ).on(type, listener);
}
</script>

<template>
    <div class="area-map">
        <div
            class="area-toolbar"
            role="toolbar"
            :aria-label="$gettext('Area tools')"
        >
            <Button
                size="small"
                icon="pi pi-pencil"
                :label="
                    isDrawing
                        ? $gettext('Stop Drawing')
                        : $gettext('Draw Polygon')
                "
                :aria-pressed="isDrawing"
                @click="startDrawing"
            />
            <Button
                size="small"
                severity="secondary"
                variant="outlined"
                icon="pi pi-trash"
                :label="$gettext('Delete Selected')"
                :disabled="!hasSelection"
                @click="deleteSelected"
            />
            <Button
                size="small"
                severity="secondary"
                variant="outlined"
                icon="pi pi-times"
                :label="$gettext('Clear Area')"
                :disabled="!polygonCount"
                @click="clearArea"
            />
            <Select
                v-if="config.basemaps.length > 1"
                v-model="basemapId"
                class="basemap-picker"
                :options="config.basemaps"
                option-label="name"
                option-value="id"
                size="small"
                :aria-label="$gettext('Basemap')"
            />
        </div>
        <div
            ref="container"
            class="map-container"
            :class="{ drawing: isDrawing }"
        />
        <p
            class="area-status"
            role="status"
        >
            {{ status }}
        </p>
    </div>
</template>

<style scoped>
.area-map {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    max-inline-size: 90rem;
}

.area-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
}

.basemap-picker {
    margin-inline-start: auto;
}

.map-container {
    block-size: 36rem;
    background: var(--p-abac-surface-bg);
    border: 0.1rem solid var(--p-abac-border);
    border-radius: 0.6rem;
    overflow: hidden;
}

.map-container:focus-within {
    outline: 0.2rem solid var(--p-abac-accent);
    outline-offset: 0.2rem;
}

.map-container.drawing :deep(.maplibregl-canvas-container) {
    cursor: crosshair;
}

.area-status {
    margin: 0;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}
</style>
