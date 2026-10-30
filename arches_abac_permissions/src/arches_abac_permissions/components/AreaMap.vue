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

import { areaOf, polygonsOf } from "@/arches_abac_permissions/geometry.ts";

import type { Feature, Polygon, Position } from "geojson";
import type {
    LngLatBoundsLike,
    StyleSpecification,
    LayerSpecification,
} from "maplibre-gl";
import type { AreaGeometry, MapConfig } from "@/arches_abac_permissions/types";

// Serve the worker as a webpack-emitted asset, as arches core does.
setWorkerUrl(
    new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).href,
);
new URL("maplibre-gl/dist/maplibre-gl-shared.mjs?asset", import.meta.url);

const DRAW_POLYGON = "draw_polygon";
const SIMPLE_SELECT = "simple_select";

const { $gettext, $ngettext } = useGettext();

const props = defineProps<{ config: MapConfig; describedBy?: string }>();
const area = defineModel<AreaGeometry | undefined>({ required: true });

const container = ref<HTMLElement>();
const isDrawing = ref(false);
const hasSelection = ref(false);

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

let map: MapLibreMap | null = null;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let draw: any = null;
// The area last read from the map, to tell our own updates from outside ones.
let syncedArea = "";
let isLoaded = false;

// Layers without their source are dropped; one would stop the style loading.
function buildStyle(): StyleSpecification {
    const sources = props.config.basemap?.sources ?? {};
    const layers = (props.config.basemap?.layers ?? []).filter(
        (layer) => !layer.source || (layer.source as string) in sources,
    );
    return {
        version: 8,
        ...(props.config.sprite ? { sprite: props.config.sprite } : {}),
        ...(props.config.glyphs ? { glyphs: props.config.glyphs } : {}),
        sources,
        layers: [
            {
                id: "abac-background",
                type: "background",
                paint: { "background-color": "#f5f6fa" },
            },
            ...(layers as LayerSpecification[]),
        ],
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

function showArea(geometry: AreaGeometry | undefined, fit: boolean) {
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

function readArea() {
    const geometries = draw
        .getAll()
        .features.map((feature: Feature) => feature.geometry);
    const next = areaOf(geometries);
    syncedArea = JSON.stringify(next ?? null);
    area.value = next;
}

function startDrawing() {
    draw?.changeMode(isDrawing.value ? SIMPLE_SELECT : DRAW_POLYGON);
    isDrawing.value = !isDrawing.value;
}

function deleteSelected() {
    draw?.trash();
    readArea();
}

function clearArea() {
    draw?.deleteAll();
    isDrawing.value = false;
    readArea();
}

watch(area, (geometry) => {
    if (JSON.stringify(geometry ?? null) !== syncedArea) {
        showArea(geometry, true);
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
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    map.addControl(draw as any);
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

// Draw events aren't part of maplibre's typed event map.
function onDraw<T>(type: string, listener: (event: T) => void) {
    (
        map as unknown as {
            on: (type: string, listener: (event: T) => void) => void;
        }
    ).on(type, listener);
}

onBeforeUnmount(() => {
    map?.remove();
    map = null;
    draw = null;
    isLoaded = false;
});
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
        </div>
        <!-- Vue must not bind classes on maplibre's container; it'd drop maplibre's own. -->
        <div
            class="map-frame"
            :class="{ drawing: isDrawing }"
        >
            <div
                ref="container"
                class="map-container"
            ></div>
        </div>
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
    max-width: 90rem;
}

.area-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
}

.map-frame {
    height: 36rem;
    border: 1px solid var(--abac-border);
    border-radius: 0.6rem;
    overflow: hidden;
}

.map-container {
    position: relative;
    height: 100%;
}

.map-frame:focus-within {
    outline: 2px solid var(--abac-accent);
    outline-offset: 2px;
}

.map-frame.drawing :deep(.maplibregl-canvas-container) {
    cursor: crosshair;
}

.area-status {
    margin: 0;
    font-size: 1.15rem;
    color: var(--abac-text-secondary);
}
</style>
