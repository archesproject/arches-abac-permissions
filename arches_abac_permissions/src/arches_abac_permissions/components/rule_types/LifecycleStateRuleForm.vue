<script setup lang="ts">
import { computed } from "vue";
import { useGettext } from "vue3-gettext";

import Select from "openvue/select";

import type {
    LifecycleStateDefinition,
    ResourceModel,
} from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

const props = defineProps<{ resourceModels: ResourceModel[] }>();
const definition = defineModel<Partial<LifecycleStateDefinition>>({
    required: true,
});

const lifecycleStates = computed(
    () =>
        props.resourceModels.find(
            (model) => model.graphid === definition.value.graphid,
        )?.lifecycle_states ?? [],
);

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
