<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useGettext } from "vue3-gettext";

import Select from "openvue/select";
import { useToast } from "openvue/usetoast";

import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import { fetchResourceModels } from "@/arches_abac_permissions/rule_types/lifecycle_state/api.ts";

import type {
    LifecycleStateDefinition,
    ResourceModel,
} from "@/arches_abac_permissions/rule_types/lifecycle_state/types";

const { $gettext } = useGettext();
const toast = useToast();

const definition = defineModel<Partial<LifecycleStateDefinition>>({
    required: true,
});
const resourceModels = ref<ResourceModel[]>([]);
const isLoading = ref(true);

const lifecycleStates = computed(
    () =>
        resourceModels.value.find(
            (model) => model.graphid === definition.value.graphid,
        )?.lifecycle_states ?? [],
);

onMounted(async () => {
    try {
        resourceModels.value = await fetchResourceModels();
    } catch (error) {
        toast.add({
            severity: ERROR,
            life: DEFAULT_ERROR_TOAST_LIFE,
            summary: $gettext("Unable to load resource models"),
            detail: error instanceof Error ? error.message : undefined,
        });
    } finally {
        isLoading.value = false;
    }
});

function onModelChange(graphid: string | null) {
    // States belong to a model's lifecycle, so a new model resets the state.
    definition.value = { graphid: graphid ?? undefined };
}

function onStateChange(stateId: string | null) {
    definition.value = {
        ...definition.value,
        lifecycle_state_id: stateId ?? undefined,
    };
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
            :loading="isLoading"
            option-label="name"
            option-value="graphid"
            filter
            :placeholder="$gettext('Select a resource model…')"
            @update:model-value="onModelChange"
        />
    </div>
    <div class="field">
        <label for="abac-lifecycle-state">{{
            $gettext("Lifecycle State")
        }}</label>
        <Select
            input-id="abac-lifecycle-state"
            :model-value="definition.lifecycle_state_id"
            :options="lifecycleStates"
            option-label="name"
            option-value="id"
            :disabled="!definition.graphid"
            :placeholder="$gettext('Select a lifecycle state…')"
            @update:model-value="onStateChange"
        />
    </div>
</template>
