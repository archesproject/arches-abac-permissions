<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from "vue";
import { useGettext } from "vue3-gettext";

import { MapComponent } from "@/arches_vue_components/components";

import {
    areaOf,
    partsOf,
    toFeatureCollection,
} from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";

import type { FeatureCollection } from "geojson";
import type { AreaGeometry } from "@/arches_abac_permissions/rule-types/spatial/types";

const METERS = "meters";
const STATUS_TYPES = [
    { types: ["Polygon"], one: "%{count} polygon", many: "%{count} polygons" },
    { types: ["Point"], one: "%{count} point", many: "%{count} points" },
    { types: ["LineString"], one: "%{count} line", many: "%{count} lines" },
];

const props = defineProps<{
    buffer?: number;
    describedBy?: string;
}>();
const area = defineModel<AreaGeometry | undefined>({ required: true });

const { $gettext, $ngettext } = useGettext();

const mapRef = useTemplateRef<InstanceType<typeof MapComponent>>("map");
const bufferDistance = computed(() => props.buffer ?? 0);

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

watch(bufferDistance, applyBuffer);
watch(area, syncMap);

function areaKey(geometry: AreaGeometry | undefined): string {
    return JSON.stringify(areaOf(partsOf(geometry)) ?? null);
}

function withBuffer(collection: FeatureCollection): FeatureCollection {
    for (const feature of collection.features) {
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
        if (feature.properties?.buffer_distance !== bufferDistance.value) {
            context!.setBufferForFeature(feature, bufferDistance.value, METERS);
        }
    }
}

function onValueUpdate(collection: FeatureCollection): void {
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
