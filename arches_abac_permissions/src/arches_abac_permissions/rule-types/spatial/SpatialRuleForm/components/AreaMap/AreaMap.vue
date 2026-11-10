<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from "vue";
import { useGettext } from "vue3-gettext";

import {
    MapComponent,
    useDefaultMapInteractionTools,
} from "@/arches_vue_components/components";

import {
    areaOf,
    partsOf,
    toFeatureCollection,
} from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";

import type { Feature, FeatureCollection } from "geojson";
import type { AreaGeometry } from "@/arches_abac_permissions/rule-types/spatial/types";

const METERS = "meters";
const MAX_BUFFER = 100000;
const METERS_PER_UNIT: Record<string, number> = {
    meters: 1,
    kilometers: 1000,
    feet: 0.3048,
    yards: 0.9144,
    miles: 1609.344,
};
const TOOL_COUNT = 3; // Map Tools, Basemap, Overlays
const STATUS_TYPES = [
    { types: ["Polygon"], one: "%{count} polygon", many: "%{count} polygons" },
    { types: ["Point"], one: "%{count} point", many: "%{count} points" },
    { types: ["LineString"], one: "%{count} line", many: "%{count} lines" },
];

const props = defineProps<{
    buffer?: number;
    describedBy?: string;
}>();
const emit = defineEmits<{
    (event: "update:buffer", payload: number): void;
}>();
const area = defineModel<AreaGeometry | undefined>({ required: true });

const { $gettext, $ngettext } = useGettext();

const interactionTools = useDefaultMapInteractionTools().slice(0, TOOL_COUNT);

const mapRef = useTemplateRef<InstanceType<typeof MapComponent>>("map");
// The definition holds one buffer; whichever shape's buffer the user edits in
// the map tools becomes the buffer for every shape.
const bufferDistance = ref(props.buffer ?? 0);
// Features we hand to the map get ids here, so edits to them are recognised
// even though the map doesn't emit for its initial value.
const knownFeatureIds = new Set<string>();
let nextFeatureId = 0;

// Only the initial value is read by the map; later changes go through
// syncMap and update:value.
const initialValue = withBuffer(toFeatureCollection(area.value));

const parts = computed(() => partsOf(area.value));
const status = computed(() => {
    const counts = STATUS_TYPES.map(({ types, one, many }) => {
        const count = parts.value.filter((part) =>
            types.includes(part.type),
        ).length;
        return count
            ? $ngettext(one, many, count, { count: String(count) })
            : "";
    }).filter(Boolean);
    return counts.length
        ? $gettext("The area has %{counts}.", { counts: counts.join(", ") })
        : $gettext("No area has been drawn.");
});

const syncedArea = ref(areaKey(area.value));

watch(
    () => props.buffer,
    (buffer) => {
        bufferDistance.value = buffer ?? 0;
        applyBuffer();
    },
);
watch(area, syncMap);

function areaKey(geometry: AreaGeometry | undefined): string {
    return JSON.stringify(areaOf(partsOf(geometry)) ?? null);
}

function withBuffer(collection: FeatureCollection): FeatureCollection {
    for (const feature of collection.features) {
        feature.id = `abac-${nextFeatureId++}`;
        knownFeatureIds.add(String(feature.id));
        feature.properties = {
            ...feature.properties,
            buffer_distance: bufferDistance.value,
            buffer_units: METERS,
        };
    }
    return collection;
}

// Preview only; the backend buffers the saved geometry.
function applyBuffer(): void {
    const context = mapRef.value?.context;
    for (const feature of context?.drawnFeatures.value ?? []) {
        if (
            feature.properties?.buffer_distance !== bufferDistance.value ||
            feature.properties?.buffer_units !== METERS
        ) {
            context!.setBufferForFeature(feature, bufferDistance.value, METERS);
        }
    }
}

function metersOf(feature: Feature): number {
    const properties = feature.properties ?? {};
    const factor = METERS_PER_UNIT[properties.buffer_units] ?? 1;
    const distance = Number(properties.buffer_distance);
    return Number.isFinite(distance)
        ? Math.min(Math.max(distance * factor, 0), MAX_BUFFER)
        : 0;
}

function adoptEditedBuffer(features: Feature[]): void {
    const edited = features.find(
        (feature) =>
            knownFeatureIds.has(String(feature.id)) &&
            metersOf(feature) !== bufferDistance.value,
    );
    for (const feature of features) {
        knownFeatureIds.add(String(feature.id));
    }
    if (edited) {
        bufferDistance.value = Math.round(metersOf(edited) * 100) / 100;
        emit("update:buffer", bufferDistance.value);
    }
}

function onValueUpdate(collection: FeatureCollection): void {
    adoptEditedBuffer(collection.features);
    const next = areaOf(
        collection.features.flatMap((feature) => partsOf(feature.geometry)),
    );
    const key = areaKey(next);
    if (key !== syncedArea.value) {
        syncedArea.value = key;
        area.value = next;
    }
    applyBuffer();
}

// Pushes a change made outside the map (e.g. pasted GeoJSON) onto it.
function syncMap(geometry: AreaGeometry | undefined): void {
    const key = areaKey(geometry);
    const context = mapRef.value?.context;
    if (key === syncedArea.value || !context?.map.value) {
        return;
    }
    syncedArea.value = key;
    context.deleteAllDrawnFeatures();
    context.addFeatures(withBuffer(toFeatureCollection(geometry)).features);
}
</script>

<template>
    <div class="area-map">
        <div
            class="map-frame"
            role="group"
            :aria-label="$gettext('Area map')"
            :aria-describedby="describedBy"
        >
            <MapComponent
                ref="map"
                :value="initialValue"
                :interaction-tools="interactionTools"
                @update:value="onValueUpdate"
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

.map-frame {
    block-size: 48rem;
    background: var(--p-abac-surface-bg);
    border: 0.1rem solid var(--p-abac-border);
    border-radius: 0.6rem;
    overflow: hidden;
}

.area-status {
    margin: 0;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}
</style>
