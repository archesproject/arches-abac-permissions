<script setup lang="ts">
import { useGettext } from "vue3-gettext";

import Select from "openvue/select";

import type {
    ResourceSet,
    ResourceSetDefinition,
} from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

defineProps<{ resourceSets: ResourceSet[] }>();
const definition = defineModel<Partial<ResourceSetDefinition>>({
    required: true,
});

function onSetChange(setId: string | null) {
    definition.value = { resource_set_id: setId ?? undefined };
}
</script>

<template>
    <div class="field">
        <label for="abac-resource-set">{{ $gettext("Resource Set") }}</label>
        <Select
            input-id="abac-resource-set"
            :model-value="definition.resource_set_id"
            :options="resourceSets"
            option-label="name"
            option-value="id"
            filter
            :placeholder="$gettext('Select a resource set…')"
            @update:model-value="onSetChange"
        />
    </div>
</template>
