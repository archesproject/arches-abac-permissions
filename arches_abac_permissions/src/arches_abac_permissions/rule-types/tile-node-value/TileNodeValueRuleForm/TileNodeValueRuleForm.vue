<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import { useGettext } from "vue3-gettext";

import InputText from "openvue/inputtext";
import Select from "openvue/select";
import { useToast } from "openvue/usetoast";

import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import {
    fetchControlledListItems,
    fetchLanguages,
    fetchResourceModelNodes,
    fetchResourceModels,
} from "@/arches_abac_permissions/rule-types/tile-node-value/api.ts";

import type {
    Language,
    ListItemOption,
    NodeOption,
    ResourceModel,
    TileNode,
    TileNodeValueDefinition,
} from "@/arches_abac_permissions/rule-types/tile-node-value/types";

const SELECT_DATATYPES = [
    "boolean",
    "domain-value",
    "domain-value-list",
    "reference",
];
const FILTER_THRESHOLD = 10;
const VALUE_HELP_ID = "abac-node-value-help";

const definition = defineModel<Partial<TileNodeValueDefinition>>({
    required: true,
});

const { $gettext } = useGettext();
const toast = useToast();

const resourceModels = ref<ResourceModel[]>([]);
const nodes = ref<TileNode[]>([]);
const languages = ref<Language[]>([]);
const listItems = ref<ListItemOption[]>([]);
const isLoadingModels = ref(true);
const isLoadingNodes = ref(false);
const isLoadingListItems = ref(false);
let nodesRequest = 0;
let listRequest = 0;

// Computeds only notify on change, so loaders don't rerun on every keystroke.
const graphid = computed(() => definition.value.graphid);
const node = computed(() =>
    nodes.value.find(
        (candidate) => candidate.nodeid === definition.value.nodeid,
    ),
);
const nodeOptions = computed(() =>
    nodes.value.map((candidate) => ({
        ...candidate,
        label: `${candidate.name} (${candidate.alias})`,
    })),
);
const languageOptions = computed(() => [
    { code: "", name: $gettext("Any language") },
    ...languages.value,
]);
const valueOptions = computed<NodeOption[]>(() => {
    switch (node.value?.datatype) {
        case "boolean":
            return [
                { id: "true", label: node.value.true_label ?? "" },
                { id: "false", label: node.value.false_label ?? "" },
            ];
        case "domain-value":
        case "domain-value-list":
            return node.value.options ?? [];
        case "reference":
            return listItems.value;
        default:
            return [];
    }
});
const usesSelect = computed(() =>
    SELECT_DATATYPES.includes(node.value?.datatype ?? ""),
);
const valueHelp = computed(() => {
    switch (node.value?.datatype) {
        case "date":
            return $gettext(
                "Matches the stored date exactly, e.g. in the format %{format}.",
                { format: node.value.date_format || "YYYY-MM-DD" },
            );
        case "resource-instance":
        case "resource-instance-list":
            return $gettext("The id of the related resource.");
        case "domain-value-list":
        case "reference":
            return $gettext(
                "Matches when the selected value is among the node's values.",
            );
        case "string":
        case "non-localized-string":
            return $gettext("Matches the full value exactly, including case.");
        default:
            return "";
    }
});
const valueHelpId = computed(() =>
    valueHelp.value ? VALUE_HELP_ID : undefined,
);
const valuePlaceholder = computed(() =>
    node.value?.datatype === "date"
        ? node.value.date_format || "YYYY-MM-DD"
        : $gettext("Enter a value…"),
);

watchEffect(loadResourceModels);
watchEffect(loadNodes);
watchEffect(loadLanguages);
watchEffect(loadListItems);

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
        const loaded = await fetchResourceModelNodes(selectedGraphid);
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

async function loadLanguages(): Promise<void> {
    if (node.value?.datatype !== "string" || languages.value.length) {
        return;
    }
    try {
        languages.value = await fetchLanguages();
    } catch (error) {
        showError($gettext("Unable to load languages"), error);
    }
}

async function loadListItems(): Promise<void> {
    const listId = node.value?.controlled_list_id;
    const request = ++listRequest;
    listItems.value = [];
    if (!listId) {
        return;
    }
    isLoadingListItems.value = true;
    try {
        const loaded = await fetchControlledListItems(listId);
        if (request === listRequest) {
            listItems.value = loaded;
        }
    } catch (error) {
        if (request === listRequest) {
            showError($gettext("Unable to load list items"), error);
        }
    } finally {
        if (request === listRequest) {
            isLoadingListItems.value = false;
        }
    }
}

function onModelChange(graphid: string | null): void {
    // Nodes belong to a model, so a new model resets everything else.
    definition.value = { graphid: graphid ?? undefined };
}

function onNodeChange(nodeid: string | null): void {
    definition.value = {
        graphid: definition.value.graphid,
        nodeid: nodeid ?? undefined,
    };
}

function onLanguageChange(language: string | null): void {
    definition.value = { ...definition.value, language: language || undefined };
}

function onValueChange(value: string | null | undefined): void {
    definition.value = { ...definition.value, value: value ?? undefined };
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
        <label for="abac-node">{{ $gettext("Node") }}</label>
        <Select
            input-id="abac-node"
            :model-value="definition.nodeid"
            :options="nodeOptions"
            option-label="label"
            option-value="nodeid"
            :filter="true"
            :loading="isLoadingNodes"
            :disabled="!definition.graphid"
            :placeholder="$gettext('Select a node…')"
            :empty-message="$gettext('This model has no supported nodes')"
            @update:model-value="onNodeChange"
        />
    </div>
    <div
        v-if="node?.datatype === 'string'"
        class="field"
    >
        <label for="abac-node-language">{{ $gettext("Language") }}</label>
        <Select
            input-id="abac-node-language"
            :model-value="definition.language ?? ''"
            :options="languageOptions"
            option-label="name"
            option-value="code"
            :filter="true"
            @update:model-value="onLanguageChange"
        />
    </div>
    <div
        v-if="node"
        class="field"
    >
        <label for="abac-node-value">{{ $gettext("Value") }}</label>
        <Select
            v-if="usesSelect"
            input-id="abac-node-value"
            :model-value="definition.value"
            :options="valueOptions"
            option-label="label"
            option-value="id"
            :filter="valueOptions.length > FILTER_THRESHOLD"
            :loading="isLoadingListItems"
            :placeholder="$gettext('Select a value…')"
            :pt="{ label: { 'aria-describedby': valueHelpId } }"
            @update:model-value="onValueChange"
        >
            <template #option="{ option }">
                <span
                    :style="{
                        paddingInlineStart: `${(option.depth ?? 0) * 1.6}rem`,
                    }"
                    >{{ option.label }}</span
                >
            </template>
        </Select>
        <InputText
            v-else
            id="abac-node-value"
            :model-value="definition.value"
            :inputmode="node.datatype === 'number' ? 'decimal' : undefined"
            :placeholder="valuePlaceholder"
            :aria-describedby="valueHelpId"
            @update:model-value="onValueChange"
        />
        <p
            v-if="valueHelp"
            :id="VALUE_HELP_ID"
            class="value-help"
        >
            {{ valueHelp }}
        </p>
    </div>
</template>

<style scoped>
.field .value-help {
    margin: 0;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}
</style>
