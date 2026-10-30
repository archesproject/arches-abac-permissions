<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Message from "openvue/message";
import ProgressSpinner from "openvue/progressspinner";
import Select from "openvue/select";
import Textarea from "openvue/textarea";
import { useToast } from "openvue/usetoast";

import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import {
    fetchGeometryNodes,
    fetchMapConfig,
    fetchResourceModels,
} from "@/arches_abac_permissions/rule-types/spatial/api.ts";
import { parseArea } from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";
import AreaMap from "@/arches_abac_permissions/rule-types/spatial/SpatialRuleForm/components/AreaMap/AreaMap.vue";

import type {
    AreaGeometry,
    GeometryNode,
    MapConfig,
    ResourceModel,
    SpatialDefinition,
} from "@/arches_abac_permissions/rule-types/spatial/types";

const AREA_HELP_ID = "abac-area-help";
const GEOJSON_ERROR_ID = "abac-area-geojson-error";

const definition = defineModel<Partial<SpatialDefinition>>({
    required: true,
});

const { $gettext } = useGettext();
const toast = useToast();

const resourceModels = ref<ResourceModel[]>([]);
const nodes = ref<GeometryNode[]>([]);
const mapConfig = ref<MapConfig | null>(null);
const mapError = ref("");
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
// Updates the geometry in place so the definition's key order (and thus the
// dirty check) is stable.
const area = computed({
    get: (): AreaGeometry | undefined => definition.value.geometry,
    set: (geometry: AreaGeometry | undefined) => {
        definition.value = { ...definition.value, geometry };
    },
});

watchEffect(loadResourceModels);
watchEffect(loadNodes);
watchEffect(loadMapConfig);

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

async function loadMapConfig(): Promise<void> {
    try {
        mapConfig.value = await fetchMapConfig();
    } catch (error) {
        mapError.value =
            error instanceof Error
                ? error.message
                : $gettext("Unable to load the map");
    }
}

function onModelChange(selectedGraphid: string | null): void {
    // Nodes belong to a model; the area is kept since it doesn't.
    definition.value = {
        graphid: selectedGraphid ?? undefined,
        geometry: definition.value.geometry,
    };
}

function onNodeChange(nodeid: string | null): void {
    definition.value = { ...definition.value, nodeid: nodeid ?? undefined };
}

function onGeoJsonToggle(event: Event): void {
    if ((event.target as HTMLDetailsElement).open) {
        geoJsonText.value = area.value
            ? JSON.stringify(area.value, null, 2)
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
            "Enter a GeoJSON Polygon or MultiPolygon, or a Feature or FeatureCollection of them.",
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
    <fieldset class="field area-field">
        <legend class="section-label">{{ $gettext("Area") }}</legend>
        <p
            :id="AREA_HELP_ID"
            class="area-help"
        >
            {{
                $gettext(
                    "Matches resources with a geometry that intersects the area. Choose Draw Polygon, then click to add points and click the first point or press Enter to finish. Or edit the area as GeoJSON below.",
                )
            }}
        </p>
        <AreaMap
            v-if="mapConfig"
            v-model="area"
            :config="mapConfig"
            :described-by="AREA_HELP_ID"
        />
        <Message
            v-else-if="mapError"
            severity="error"
            role="alert"
        >
            {{ mapError }}
        </Message>
        <ProgressSpinner
            v-else
            class="map-spinner"
            :aria-label="$gettext('Loading map')"
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
                <Button
                    size="small"
                    severity="secondary"
                    variant="outlined"
                    icon="pi pi-check"
                    :label="$gettext('Apply GeoJSON')"
                    @click="applyGeoJson"
                />
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

.map-spinner {
    inline-size: 3.2rem;
    block-size: 3.2rem;
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
