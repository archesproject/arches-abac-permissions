<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Message from "openvue/message";
import ProgressSpinner from "openvue/progressspinner";
import Select from "openvue/select";
import Textarea from "openvue/textarea";

import {
    fetchMapConfig,
    fetchResourceModelNodes,
} from "@/arches_abac_permissions/api.ts";
import AreaMap from "@/arches_abac_permissions/components/AreaMap.vue";
import { GEOMETRY_DATATYPE } from "@/arches_abac_permissions/constants.ts";
import { parseArea } from "@/arches_abac_permissions/geometry.ts";

import type {
    AreaGeometry,
    MapConfig,
    ResourceModel,
    SpatialDefinition,
    TileNode,
} from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

defineProps<{ resourceModels: ResourceModel[] }>();
const definition = defineModel<Partial<SpatialDefinition>>({
    required: true,
});

const nodes = ref<TileNode[]>([]);
const isLoadingNodes = ref(false);
const mapConfig = ref<MapConfig | null>(null);
const error = ref("");
const geoJsonText = ref("");
const geoJsonError = ref("");

const nodeOptions = computed(() =>
    nodes.value.map((node) => ({
        ...node,
        label: `${node.name} (${node.alias})`,
    })),
);
const area = computed({
    get: () => definition.value.geometry,
    set: (geometry: AreaGeometry | undefined) => {
        definition.value = { ...definition.value, geometry };
    },
});

function describeError(fallback: string, caught: unknown) {
    error.value = caught instanceof Error ? caught.message : fallback;
}

let nodesRequest = 0;
watch(
    () => definition.value.graphid,
    async (graphid) => {
        const request = ++nodesRequest;
        nodes.value = [];
        if (!graphid) {
            return;
        }
        isLoadingNodes.value = true;
        try {
            const loaded = await fetchResourceModelNodes(
                graphid,
                GEOMETRY_DATATYPE,
            );
            if (request === nodesRequest) {
                nodes.value = loaded;
            }
        } catch (caught) {
            if (request === nodesRequest) {
                describeError($gettext("Unable to load nodes"), caught);
            }
        } finally {
            if (request === nodesRequest) {
                isLoadingNodes.value = false;
            }
        }
    },
    { immediate: true },
);

fetchMapConfig()
    .then((config) => (mapConfig.value = config))
    .catch((caught) =>
        describeError($gettext("Unable to load the map"), caught),
    );

function onModelChange(graphid: string | null) {
    // Nodes belong to a model; the area is kept since it doesn't.
    definition.value = {
        graphid: graphid ?? undefined,
        geometry: definition.value.geometry,
    };
}

function onNodeChange(nodeid: string | null) {
    definition.value = { ...definition.value, nodeid: nodeid ?? undefined };
}

function onGeoJsonToggle(event: Event) {
    if ((event.target as HTMLDetailsElement).open) {
        geoJsonText.value = area.value
            ? JSON.stringify(area.value, null, 2)
            : "";
        geoJsonError.value = "";
    }
}

function applyGeoJson() {
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
            option-label="name"
            option-value="graphid"
            filter
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
            filter
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
            id="abac-area-help"
            class="area-help"
        >
            {{
                $gettext(
                    "Matches resources with a geometry that intersects the area.",
                )
            }}
        </p>
        <AreaMap
            v-if="mapConfig"
            v-model="area"
            :config="mapConfig"
            described-by="abac-area-help"
        />
        <ProgressSpinner
            v-else-if="!error"
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
                ></i>
                {{ $gettext("Edit as GeoJSON") }}
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
                        geoJsonError ? 'abac-area-geojson-error' : undefined
                    "
                />
                <p
                    v-if="geoJsonError"
                    id="abac-area-geojson-error"
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
    <Message
        v-if="error"
        severity="error"
        role="alert"
    >
        {{ error }}
    </Message>
</template>

<style scoped>
.area-field {
    margin: 0;
    padding: 0;
    border: 0;
    min-width: 0;
}

.area-help {
    margin: 0;
    font-size: 1.15rem;
    color: var(--abac-text-secondary);
}

.map-spinner {
    width: 3.2rem;
    height: 3.2rem;
}

.geojson {
    max-width: 90rem;
    font-size: 1.2rem;
    color: var(--abac-text-secondary);
}

.geojson summary {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    border-radius: 0.4rem;
}

.geojson summary:focus-visible {
    outline: 2px solid var(--abac-accent);
    outline-offset: 2px;
}

.geojson-body {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.8rem;
    margin-top: 0.8rem;
}

.geojson-body :deep(textarea) {
    width: 100%;
    font-family: monospace;
    font-size: 1.15rem;
}

.geojson-error {
    margin: 0;
    color: var(--abac-danger);
}
</style>
