<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import InputText from "openvue/inputtext";
import Message from "openvue/message";
import Select from "openvue/select";

import {
    fetchControlledListItems,
    fetchLanguages,
    fetchResourceModelNodes,
} from "@/arches_abac_permissions/api.ts";

import type {
    Language,
    ListItemOption,
    NodeOption,
    ResourceModel,
    TileNode,
    TileNodeValueDefinition,
} from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

defineProps<{ resourceModels: ResourceModel[] }>();
const definition = defineModel<Partial<TileNodeValueDefinition>>({
    required: true,
});

const nodes = ref<TileNode[]>([]);
const languages = ref<Language[]>([]);
const listItems = ref<ListItemOption[]>([]);
const isLoadingNodes = ref(false);
const isLoadingListItems = ref(false);
const error = ref("");

const SELECT_DATATYPES = [
    "boolean",
    "domain-value",
    "domain-value-list",
    "reference",
];

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

function describeError(fallback: string, caught: unknown) {
    error.value = caught instanceof Error ? caught.message : fallback;
}

let nodesRequest = 0;
watch(
    () => definition.value.graphid,
    async (graphid) => {
        const request = ++nodesRequest;
        nodes.value = [];
        error.value = "";
        if (!graphid) {
            return;
        }
        isLoadingNodes.value = true;
        try {
            const loaded = await fetchResourceModelNodes(graphid);
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

watch(
    () => node.value?.datatype,
    async (datatype) => {
        if (datatype !== "string" || languages.value.length) {
            return;
        }
        try {
            languages.value = await fetchLanguages();
        } catch (caught) {
            describeError($gettext("Unable to load languages"), caught);
        }
    },
    { immediate: true },
);

let listRequest = 0;
watch(
    () => node.value?.controlled_list_id,
    async (listId) => {
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
        } catch (caught) {
            if (request === listRequest) {
                describeError($gettext("Unable to load list items"), caught);
            }
        } finally {
            if (request === listRequest) {
                isLoadingListItems.value = false;
            }
        }
    },
    { immediate: true },
);

function onModelChange(graphid: string | null) {
    // Nodes belong to a model, so a new model resets everything else.
    definition.value = { graphid: graphid ?? undefined };
}

function onNodeChange(nodeid: string | null) {
    definition.value = {
        graphid: definition.value.graphid,
        nodeid: nodeid ?? undefined,
    };
}

function onLanguageChange(language: string | null) {
    definition.value = { ...definition.value, language: language || undefined };
}

function onValueChange(value: string | null | undefined) {
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
            option-label="name"
            option-value="graphid"
            filter
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
            filter
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
            filter
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
            :filter="valueOptions.length > 10"
            :loading="isLoadingListItems"
            :placeholder="$gettext('Select a value…')"
            :pt="{
                label: {
                    'aria-describedby': valueHelp
                        ? 'abac-node-value-help'
                        : undefined,
                },
            }"
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
            :placeholder="
                node.datatype === 'date'
                    ? node.date_format || 'YYYY-MM-DD'
                    : $gettext('Enter a value…')
            "
            :aria-describedby="valueHelp ? 'abac-node-value-help' : undefined"
            @update:model-value="onValueChange"
        />
        <p
            v-if="valueHelp"
            id="abac-node-value-help"
            class="value-help"
        >
            {{ valueHelp }}
        </p>
    </div>
    <Message
        v-if="error"
        severity="error"
        role="alert"
    >
        {{ error }}
    </Message>
</template>

<style scoped>
.value-help {
    margin: 0;
    font-size: 1.15rem;
    color: var(--abac-text-secondary);
}
</style>
