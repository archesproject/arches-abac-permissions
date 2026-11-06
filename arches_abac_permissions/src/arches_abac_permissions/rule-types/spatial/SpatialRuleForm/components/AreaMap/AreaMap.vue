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
import bufferGeometry from "@turf/buffer";

import Button from "openvue/button";
import Checkbox from "openvue/checkbox";
import Select from "openvue/select";

import {
    areaOf,
    partsOf,
    positionsOf,
    toFeatureCollection,
} from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";
import {
    buildStyle,
    layerIdsOf,
} from "@/arches_abac_permissions/rule-types/spatial/map-style.ts";

import type { Feature, FeatureCollection } from "geojson";
import type { GeoJSONSource, IControl, LngLatBoundsLike } from "maplibre-gl";
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
const DRAW_POINT = "draw_point";
const DRAW_LINE = "draw_line_string";
const SIMPLE_SELECT = "simple_select";
const BUFFER_SOURCE = "abac-buffer-preview";
const BUFFER_FILL_LAYER = "abac-buffer-preview-fill";
const BUFFER_LINE_LAYER = "abac-buffer-preview-line";
const BUFFER_COLOR = "#e07b00";
const BUFFER_FILL_OPACITY = 0.25;
const BUFFER_LINE_WIDTH = 2;
const BASEMAP_SELECT_ID = "abac-basemap";

const props = defineProps<{
    config: MapConfig;
    buffer?: number;
    describedBy?: string;
}>();
const area = defineModel<AreaGeometry | undefined>({ required: true });

const { $gettext, $ngettext } = useGettext();

const container = ref<HTMLElement>();
const drawMode = ref(SIMPLE_SELECT);
const hasSelection = ref(false);
const selectedBasemap = ref<string | null>(
    props.config.default_basemap ?? props.config.basemaps[0]?.name ?? null,
);
const visibleOverlays = ref<Record<string, boolean>>({});

let map: MapLibreMap | null = null;
let draw: DrawControl | null = null;
// The area last read from the map, to tell our own updates from outside ones.
let syncedArea = "";
let isLoaded = false;

const parts = computed(() => partsOf(area.value));
const partCount = computed(() => parts.value.length);
const status = computed(() => {
    const counts = [
        {
            types: ["Polygon"],
            one: "%{count} polygon",
            many: "%{count} polygons",
        },
        { types: ["Point"], one: "%{count} point", many: "%{count} points" },
        { types: ["LineString"], one: "%{count} line", many: "%{count} lines" },
    ]
        .map(({ types, one, many }) => {
            const count = parts.value.filter((part) =>
                types.includes(part.type),
            ).length;
            return count
                ? $ngettext(one, many, count, { count: String(count) })
                : "";
        })
        .filter(Boolean);
    return counts.length
        ? $gettext("The area has %{counts}.", { counts: counts.join(", ") })
        : $gettext("No area has been drawn.");
});
const isDrawing = computed(() => drawMode.value !== SIMPLE_SELECT);
const showBasemapSelect = computed(() => props.config.basemaps.length > 1);

watch(selectedBasemap, applyVisibility);
watch(visibleOverlays, applyVisibility, { deep: true });
watch(
    () => props.buffer,
    () => showBuffer(area.value),
);

watch(area, (geometry) => {
    if (JSON.stringify(geometry ?? null) !== syncedArea) {
        showArea(geometry, true);
    }
});

onMounted(() => {
    const bounds = boundsOf(area.value) ?? props.config.bounds ?? undefined;
    map = new MapLibreMap({
        container: container.value!,
        style: buildStyle(props.config),
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
        addBufferLayers();
        applyVisibility();
        showArea(area.value, false);
    });
    onDraw("draw.create", readArea);
    onDraw("draw.update", readArea);
    onDraw("draw.delete", readArea);
    onDraw<{ mode: string }>("draw.modechange", (event) => {
        drawMode.value = event.mode;
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

// Only visibility changes; setStyle would drop the draw layers.
function applyVisibility(): void {
    if (!map || !isLoaded) {
        return;
    }
    const entries = [
        ...props.config.basemaps.map((entry) => ({
            name: entry.name,
            isVisible: entry.name === selectedBasemap.value,
        })),
        ...props.config.overlays.map((entry) => ({
            name: entry.name,
            isVisible: Boolean(visibleOverlays.value[entry.name]),
        })),
    ];
    for (const { name, isVisible } of entries) {
        for (const id of layerIdsOf(props.config, name)) {
            if (map.getLayer(id)) {
                map.setLayoutProperty(
                    id,
                    "visibility",
                    isVisible ? "visible" : "none",
                );
            }
        }
    }
}

function addBufferLayers(): void {
    if (!map) {
        return;
    }
    map.addSource(BUFFER_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
        id: BUFFER_FILL_LAYER,
        type: "fill",
        source: BUFFER_SOURCE,
        paint: {
            "fill-color": BUFFER_COLOR,
            "fill-opacity": BUFFER_FILL_OPACITY,
        },
    });
    map.addLayer({
        id: BUFFER_LINE_LAYER,
        type: "line",
        source: BUFFER_SOURCE,
        paint: { "line-color": BUFFER_COLOR, "line-width": BUFFER_LINE_WIDTH },
    });
    showBuffer(area.value);
}

// A preview only; the backend computes the authoritative buffer.
function showBuffer(geometry: AreaGeometry | undefined): void {
    const source = map?.getSource(BUFFER_SOURCE) as GeoJSONSource | undefined;
    if (!source) {
        return;
    }
    let preview: FeatureCollection = {
        type: "FeatureCollection",
        features: [],
    };
    if (props.buffer && props.buffer > 0 && geometry) {
        try {
            const buffered = bufferGeometry(
                toFeatureCollection(geometry),
                props.buffer,
                {
                    units: "meters",
                },
            );
            preview = buffered ?? preview;
        } catch {
            preview = { type: "FeatureCollection", features: [] };
        }
    }
    source.setData(preview);
}

function boundsOf(geometry: AreaGeometry | undefined): LngLatBoundsLike | null {
    const positions = positionsOf(geometry);
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
    draw.set(toFeatureCollection(geometry));
    showBuffer(geometry);
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
    showBuffer(next);
}

function toggleDrawing(mode: string): void {
    const next = drawMode.value === mode ? SIMPLE_SELECT : mode;
    draw?.changeMode(next);
    drawMode.value = next;
}

function deleteSelected(): void {
    draw?.trash();
    readArea();
}

function clearArea(): void {
    draw?.deleteAll();
    drawMode.value = SIMPLE_SELECT;
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
            v-if="showBasemapSelect || config.overlays.length"
            class="map-layers"
        >
            <div
                v-if="showBasemapSelect"
                class="layer-field"
            >
                <label :for="BASEMAP_SELECT_ID">{{
                    $gettext("Basemap")
                }}</label>
                <Select
                    v-model="selectedBasemap"
                    :input-id="BASEMAP_SELECT_ID"
                    :options="config.basemaps"
                    option-label="name"
                    option-value="name"
                />
            </div>
            <fieldset
                v-if="config.overlays.length"
                class="overlays"
            >
                <legend>{{ $gettext("Overlays") }}</legend>
                <div
                    v-for="(overlay, index) in config.overlays"
                    :key="overlay.name"
                    class="overlay-option"
                >
                    <Checkbox
                        v-model="visibleOverlays[overlay.name]"
                        :input-id="`abac-overlay-${index}`"
                        :binary="true"
                    />
                    <label :for="`abac-overlay-${index}`">{{
                        overlay.name
                    }}</label>
                </div>
            </fieldset>
        </div>
        <div
            class="area-toolbar"
            role="toolbar"
            :aria-label="$gettext('Area tools')"
        >
            <Button
                size="small"
                icon="pi pi-pencil"
                :label="
                    drawMode === DRAW_POLYGON
                        ? $gettext('Stop Drawing')
                        : $gettext('Draw Polygon')
                "
                :aria-pressed="drawMode === DRAW_POLYGON"
                @click="toggleDrawing(DRAW_POLYGON)"
            />
            <Button
                size="small"
                icon="pi pi-map-marker"
                :label="
                    drawMode === DRAW_POINT
                        ? $gettext('Stop Drawing')
                        : $gettext('Draw Point')
                "
                :aria-pressed="drawMode === DRAW_POINT"
                @click="toggleDrawing(DRAW_POINT)"
            />
            <Button
                size="small"
                icon="pi pi-minus"
                :label="
                    drawMode === DRAW_LINE
                        ? $gettext('Stop Drawing')
                        : $gettext('Draw Line')
                "
                :aria-pressed="drawMode === DRAW_LINE"
                @click="toggleDrawing(DRAW_LINE)"
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
                :disabled="!partCount"
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
            />
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
    max-inline-size: 90rem;
}

.map-layers {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 1.6rem;
}

.layer-field,
.overlay-option {
    display: flex;
    gap: 0.6rem;
}

.layer-field {
    flex-direction: column;
    min-inline-size: 20rem;
}

.overlays {
    display: flex;
    flex-wrap: wrap;
    gap: 1.2rem;
    margin: 0;
    padding: 0;
    border: 0;
}

.overlays legend {
    padding: 0;
    margin-block-end: 0.6rem;
}

.overlay-option {
    align-items: center;
}

.area-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
}

.map-frame {
    block-size: 36rem;
    background: var(--p-abac-surface-bg);
    border: 0.1rem solid var(--p-abac-border);
    border-radius: 0.6rem;
    overflow: hidden;
}

.map-container {
    position: relative;
    block-size: 100%;
}

.map-frame:focus-within {
    outline: 0.2rem solid var(--p-abac-accent);
    outline-offset: 0.2rem;
}

.map-frame.drawing :deep(.maplibregl-canvas-container) {
    cursor: crosshair;
}

.area-status {
    margin: 0;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}
</style>
