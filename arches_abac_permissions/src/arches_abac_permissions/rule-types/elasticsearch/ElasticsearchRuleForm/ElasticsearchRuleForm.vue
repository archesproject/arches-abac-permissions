<script setup lang="ts">
import { ref, watchEffect } from "vue";
import { useGettext } from "vue3-gettext";

import Select from "openvue/select";
import Textarea from "openvue/textarea";
import { useToast } from "openvue/usetoast";

import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import { fetchSavedSearches } from "@/arches_abac_permissions/rule-types/elasticsearch/api.ts";

import type {
    ElasticsearchDefinition,
    SavedSearch,
} from "@/arches_abac_permissions/rule-types/elasticsearch/types";

const { $gettext } = useGettext();
const toast = useToast();

const definition = defineModel<Partial<ElasticsearchDefinition>>({
    required: true,
});
const savedSearches = ref<SavedSearch[]>([]);
const isLoading = ref(true);

watchEffect(loadSavedSearches);

function onQueryChange(queryString: string | undefined): void {
    definition.value = { query_string: queryString ?? "" };
}

async function loadSavedSearches(): Promise<void> {
    try {
        savedSearches.value = await fetchSavedSearches();
    } catch (error) {
        toast.add({
            severity: ERROR,
            life: DEFAULT_ERROR_TOAST_LIFE,
            summary: $gettext("Unable to load saved searches"),
            detail: error instanceof Error ? error.message : undefined,
        });
    } finally {
        isLoading.value = false;
    }
}
</script>

<template>
    <div class="field">
        <label for="abac-elasticsearch-saved-search">{{
            $gettext("Saved Search")
        }}</label>
        <Select
            input-id="abac-elasticsearch-saved-search"
            option-label="name"
            option-value="url"
            :model-value="definition.query_string"
            :options="savedSearches"
            :loading="isLoading"
            :placeholder="$gettext('Copy a saved search…')"
            :empty-message="$gettext('There are no saved searches')"
            @update:model-value="onQueryChange"
        />
    </div>
    <div class="field">
        <label for="abac-elasticsearch-query">{{ $gettext("Search") }}</label>
        <Textarea
            id="abac-elasticsearch-query"
            rows="3"
            :auto-resize="true"
            :model-value="definition.query_string"
            :placeholder="
                $gettext('Paste the address of a search from the search page…')
            "
            @update:model-value="onQueryChange"
        />
        <small>{{
            $gettext(
                "Uses the search's filters. Paging and sorting are ignored. A saved search is copied, so later changes to it don't change the rule.",
            )
        }}</small>
    </div>
</template>
