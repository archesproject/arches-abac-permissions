<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Select from "openvue/select";
import Textarea from "openvue/textarea";
import { useToast } from "openvue/usetoast";

import {
    DEFAULT_ERROR_TOAST_LIFE,
    DEFAULT_SUCCESS_TOAST_LIFE,
    ERROR,
    SUCCESS,
} from "@/arches_abac_permissions/constants.ts";
import {
    fetchGeometryNodes,
    fetchResourceModels,
} from "@/arches_abac_permissions/rule-types/spatial/api.ts";
import {
    needsBuffer,
    parseArea,
    toFeatureCollection,
} from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";
import AreaMap from "@/arches_abac_permissions/rule-types/spatial/SpatialRuleForm/components/AreaMap/AreaMap.vue";

import type {
    AreaGeometry,
    GeometryNode,
    ResourceModel,
    SpatialDefinition,
    SpatialOperator,
} from "@/arches_abac_permissions/rule-types/spatial/types";

const AREA_HELP_ID = "abac-area-help";
const GEOJSON_ERROR_ID = "abac-area-geojson-error";
const MAX_BUFFER = 100000;
const DEFAULT_OPERATOR: SpatialOperator = "intersects";

const definition = defineModel<Partial<SpatialDefinition>>({
    required: true,
});

const { $gettext } = useGettext();
const toast = useToast();

const resourceModels = ref<ResourceModel[]>([]);
const nodes = ref<GeometryNode[]>([]);
const isLoadingModels = ref(true);
const isLoadingNodes = ref(false);
const geoJsonText = ref("");
const geoJsonError = ref("");
let nodesRequest = 0;

// Computeds only notify on change, so loaders don't rerun on every edit.
const graphid = computed(() => definition.value.graphid);
const nodeOptions = computed(() =>
    nodes.value.map((node) => ({
        ...node,
        label: `${node.name} (${node.alias})`,
    })),
);
const operator = computed(
    (): SpatialOperator => definition.value.operator ?? DEFAULT_OPERATOR,
);
const operatorOptions = computed(
    (): { value: SpatialOperator; label: string; help: string }[] => [
        {
            value: "intersects",
            label: $gettext("Touches or overlaps the area"),
            help: $gettext(
                "Matches resources with a geometry in the node that touches or overlaps the area.",
            ),
        },
        {
            value: "within",
            label: $gettext("Is entirely inside the area"),
            help: $gettext(
                "Matches resources whose geometries in the node all lie inside the area.",
            ),
        },
        {
            value: "centroid",
            label: $gettext("Has its centre in the area"),
            help: $gettext(
                "Matches resources with a geometry in the node whose centre is in the area.",
            ),
        },
    ],
);
const areaHelp = computed(
    (): string =>
        operatorOptions.value.find((option) => option.value === operator.value)
            ?.help ?? "",
);
// Updates the geometry in place so the definition's key order (and thus the
// dirty check) is stable.
const area = computed({
    get: (): AreaGeometry | undefined => definition.value.geometry,
    set: (geometry: AreaGeometry | undefined) => {
        definition.value = { ...definition.value, geometry };
    },
});

const requiresBuffer = computed(() => needsBuffer(area.value));

watchEffect(loadResourceModels);
watchEffect(loadNodes);

function showError(summary: string, error: unknown): void {
    toast.add({
        severity: ERROR,
        life: DEFAULT_ERROR_TOAST_LIFE,
        summary,
        detail: error instanceof Error ? error.message : undefined,
    });
}

async function loadResourceModels(): Promise<void> {
    try {
        resourceModels.value = await fetchResourceModels();
    } catch (error) {
        showError($gettext("Unable to load resource models"), error);
    } finally {
        isLoadingModels.value = false;
    }
}

async function loadNodes(): Promise<void> {
    const selectedGraphid = graphid.value;
    const request = ++nodesRequest;
    nodes.value = [];
    if (!selectedGraphid) {
        return;
    }
    isLoadingNodes.value = true;
    try {
        const loaded = await fetchGeometryNodes(selectedGraphid);
        if (request === nodesRequest) {
            nodes.value = loaded;
        }
    } catch (error) {
        if (request === nodesRequest) {
            showError($gettext("Unable to load nodes"), error);
        }
    } finally {
        if (request === nodesRequest) {
            isLoadingNodes.value = false;
        }
    }
}

function onModelChange(selectedGraphid: string | null): void {
    // Nodes belong to a model; the area and operator don't.
    definition.value = {
        graphid: selectedGraphid ?? undefined,
        geometry: definition.value.geometry,
        buffer: definition.value.buffer,
        operator: definition.value.operator,
    };
}

function onNodeChange(nodeid: string | null): void {
    definition.value = { ...definition.value, nodeid: nodeid ?? undefined };
}

function onOperatorChange(selected: SpatialOperator | null): void {
    definition.value = {
        ...definition.value,
        operator: selected ?? DEFAULT_OPERATOR,
    };
}

function onBufferChange(meters: number): void {
    const rest = { ...definition.value };
    delete rest.buffer;
    definition.value = meters ? { ...rest, buffer: meters } : rest;
}

async function copyGeoJson(): Promise<void> {
    try {
        await navigator.clipboard.writeText(
            JSON.stringify(toFeatureCollection(area.value), null, 2),
        );
        toast.add({
            severity: SUCCESS,
            life: DEFAULT_SUCCESS_TOAST_LIFE,
            summary: $gettext("GeoJSON copied"),
        });
    } catch (error) {
        showError($gettext("Unable to copy GeoJSON"), error);
    }
}

function onGeoJsonToggle(event: Event): void {
    if ((event.target as HTMLDetailsElement).open) {
        geoJsonText.value = area.value
            ? JSON.stringify(toFeatureCollection(area.value), null, 2)
            : "";
        geoJsonError.value = "";
    }
}

function applyGeoJson(): void {
    if (!geoJsonText.value.trim()) {
        area.value = undefined;
        geoJsonError.value = "";
        return;
    }
    try {
        area.value = parseArea(geoJsonText.value);
        geoJsonError.value = "";
    } catch {
        geoJsonError.value = $gettext(
            "Enter GeoJSON polygons, points or lines as a geometry, Feature, FeatureCollection or GeometryCollection.",
        );
    }
}
</script>

<template>
    <div class="field">
        <label for="abac-resource-model">{{
            $gettext("Resource Model")
        }}</label>
        <Select
            input-id="abac-resource-model"
            :model-value="definition.graphid"
            :options="resourceModels"
            :loading="isLoadingModels"
            option-label="name"
            option-value="graphid"
            :filter="true"
            :placeholder="$gettext('Select a resource model…')"
            @update:model-value="onModelChange"
        />
    </div>
    <div class="field">
        <label for="abac-geometry-node">{{ $gettext("Geometry Node") }}</label>
        <Select
            input-id="abac-geometry-node"
            :model-value="definition.nodeid"
            :options="nodeOptions"
            option-label="label"
            option-value="nodeid"
            :filter="true"
            :loading="isLoadingNodes"
            :disabled="!definition.graphid"
            :placeholder="$gettext('Select a geometry node…')"
            :empty-message="$gettext('This model has no geometry nodes')"
            @update:model-value="onNodeChange"
        />
    </div>
    <div class="field">
        <label for="abac-spatial-operator">{{
            $gettext("Spatial Relationship")
        }}</label>
        <Select
            input-id="abac-spatial-operator"
            :model-value="operator"
            :options="operatorOptions"
            option-label="label"
            option-value="value"
            @update:model-value="onOperatorChange"
        />
    </div>
    <fieldset class="field area-field">
        <legend class="section-label">{{ $gettext("Area") }}</legend>
        <p
            :id="AREA_HELP_ID"
            class="area-help"
        >
            {{ areaHelp }}
        </p>
        <p class="area-help">
            {{
                $gettext(
                    "Set a buffer for a shape in the Map Tools panel. Points and lines need a buffer greater than 0. The buffer is applied to every part of the area, up to %{max} meters.",
                    { max: String(MAX_BUFFER) },
                )
            }}
        </p>
        <AreaMap
            v-model="area"
            :buffer="definition.buffer"
            @update:buffer="onBufferChange"
            :described-by="AREA_HELP_ID"
        />
        <details
            class="geojson"
            @toggle="onGeoJsonToggle"
        >
            <summary>
                <i
                    class="pi pi-code"
                    aria-hidden="true"
                />
                <span>{{ $gettext("Edit as GeoJSON") }}</span>
            </summary>
            <div class="geojson-body">
                <label for="abac-area-geojson">{{
                    $gettext("Area GeoJSON (longitude, latitude)")
                }}</label>
                <Textarea
                    id="abac-area-geojson"
                    v-model="geoJsonText"
                    rows="8"
                    spellcheck="false"
                    :invalid="Boolean(geoJsonError)"
                    :aria-describedby="
                        geoJsonError ? GEOJSON_ERROR_ID : undefined
                    "
                />
                <p
                    v-if="geoJsonError"
                    :id="GEOJSON_ERROR_ID"
                    class="geojson-error"
                    role="alert"
                >
                    {{ geoJsonError }}
                </p>
                <div class="geojson-actions">
                    <Button
                        size="small"
                        severity="secondary"
                        variant="outlined"
                        icon="pi pi-check"
                        :label="$gettext('Apply GeoJSON')"
                        @click="applyGeoJson"
                    />
                    <Button
                        size="small"
                        severity="secondary"
                        variant="outlined"
                        icon="pi pi-copy"
                        :label="$gettext('Copy GeoJSON')"
                        :disabled="!area"
                        @click="copyGeoJson"
                    />
                </div>
            </div>
        </details>
    </fieldset>
</template>

<style scoped>
.area-field {
    margin: 0;
    padding: 0;
    border: 0;
    min-inline-size: 0;
}

.area-help {
    margin: 0;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}

.geojson-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
}

.geojson {
    max-inline-size: 90rem;
    font-size: 1.2rem;
    color: var(--p-abac-text-secondary);
}

.geojson summary {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    border-radius: 0.4rem;
}

.geojson summary:focus-visible {
    outline: 0.2rem solid var(--p-abac-accent);
    outline-offset: 0.2rem;
}

.geojson-body {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.8rem;
    padding-block-start: 0.8rem;
}

.geojson-body :deep(textarea) {
    inline-size: 100%;
    font-family: monospace;
    font-size: 1.15rem;
}

.geojson-error {
    margin: 0;
    color: var(--p-abac-danger);
}
</style>
