<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useGettext } from "vue3-gettext";

import Select from "openvue/select";
import { useToast } from "openvue/usetoast";

import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import { fetchResourceSets } from "@/arches_abac_permissions/rule_types/resource_set/api.ts";

import type {
    ResourceSet,
    ResourceSetDefinition,
} from "@/arches_abac_permissions/rule_types/resource_set/types";

const { $gettext } = useGettext();
const toast = useToast();

const definition = defineModel<Partial<ResourceSetDefinition>>({
    required: true,
});
const resourceSets = ref<ResourceSet[]>([]);
const isLoading = ref(true);

onMounted(async () => {
    try {
        resourceSets.value = await fetchResourceSets();
    } catch (error) {
        toast.add({
            severity: ERROR,
            life: DEFAULT_ERROR_TOAST_LIFE,
            summary: $gettext("Unable to load resource sets"),
            detail: error instanceof Error ? error.message : undefined,
        });
    } finally {
        isLoading.value = false;
    }
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
            :loading="isLoading"
            option-label="name"
            option-value="id"
            filter
            :placeholder="$gettext('Select a resource set…')"
            @update:model-value="onSetChange"
        />
    </div>
</template>
