<script setup lang="ts">
import { computed, ref, toRaw, watch, watchEffect } from "vue";
import { useGettext } from "vue3-gettext";

import Select from "openvue/select";
import Textarea from "openvue/textarea";
import { useToast } from "openvue/usetoast";

import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import { fetchSavedSearches } from "@/arches_abac_permissions/rule-types/search/api.ts";
import { getRuleQuery } from "@/arches_abac_permissions/rule-types/search/saved-search.ts";

import type {
    AdvancedSearchQuery,
    SavedSearch,
    SearchDefinition,
} from "@/arches_abac_permissions/rule-types/search/types";

const SAVED_SEARCH_HELP_ID = "abac-saved-search-help";
const QUERY_HELP_ID = "abac-search-query-help";
const QUERY_ERROR_ID = "abac-search-query-error";

const definition = defineModel<Partial<SearchDefinition>>({
    required: true,
});

const { $gettext } = useGettext();
const toast = useToast();

const mySavedSearches = ref<SavedSearch[]>([]);
const sharedSavedSearches = ref<SavedSearch[]>([]);
const isLoadingSavedSearches = ref(true);
const selectedSavedSearchId = ref<string | null>(null);
const queryText = ref("");
const queryError = ref("");
let emittedDefinition: Partial<SearchDefinition> | undefined;

const savedSearchGroups = computed(() =>
    [
        {
            label: $gettext("Your saved searches"),
            items: mySavedSearches.value.map((savedSearch) =>
                toOption(savedSearch, savedSearch.name),
            ),
        },
        {
            label: $gettext("Shared with you"),
            items: sharedSavedSearches.value.map((savedSearch) =>
                toOption(
                    savedSearch,
                    $gettext("%{name} (by %{username})", {
                        name: savedSearch.name,
                        username: savedSearch.creator.username,
                    }),
                ),
            ),
        },
    ].filter((group) => group.items.length > 0),
);

// The form is reused when another rule is selected, so reload the text
// whenever the definition is not one this form just emitted.
watch(
    () => definition.value,
    (current) => {
        if (toRaw(current) === emittedDefinition) {
            return;
        }
        const query = current.advanced_search_query;
        queryText.value = query ? JSON.stringify(query, null, 2) : "";
        queryError.value = "";
        selectedSavedSearchId.value = null;
    },
    { immediate: true },
);

watchEffect(loadSavedSearches);

async function loadSavedSearches(): Promise<void> {
    try {
        const { mine, shared } = await fetchSavedSearches();
        mySavedSearches.value = mine;
        sharedSavedSearches.value = shared;
    } catch (error) {
        toast.add({
            severity: ERROR,
            life: DEFAULT_ERROR_TOAST_LIFE,
            summary: $gettext("Unable to load saved searches"),
            detail: error instanceof Error ? error.message : undefined,
        });
    } finally {
        isLoadingSavedSearches.value = false;
    }
}

function toOption(
    savedSearch: SavedSearch,
    label: string,
): { id: string; label: string; disabled: boolean } {
    const isUsable = getRuleQuery(savedSearch) !== null;
    return {
        id: savedSearch.savedsearchid,
        label: isUsable
            ? label
            : $gettext("%{label}: can't be used for a rule", { label }),
        disabled: !isUsable,
    };
}

function onSavedSearchChange(savedSearchId: string | null): void {
    const savedSearch = [
        ...mySavedSearches.value,
        ...sharedSavedSearches.value,
    ].find((candidate) => candidate.savedsearchid === savedSearchId);
    const query = savedSearch ? getRuleQuery(savedSearch) : null;
    if (!query) {
        return;
    }
    queryText.value = JSON.stringify(query, null, 2);
    queryError.value = "";
    selectedSavedSearchId.value = savedSearchId;
    emitDefinition({ advanced_search_query: query });
}

function emitDefinition(value: Partial<SearchDefinition>): void {
    emittedDefinition = value;
    definition.value = value;
}

function onQueryInput(text: string | undefined): void {
    queryText.value = text ?? "";
    queryError.value = "";
    selectedSavedSearchId.value = null;
    if (!queryText.value.trim()) {
        emitDefinition({});
        return;
    }
    let parsed: unknown;
    try {
        parsed = JSON.parse(queryText.value);
    } catch {
        parsed = undefined;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        queryError.value = $gettext(
            "Paste the query as JSON: one object with a graph_slug and clauses.",
        );
        emitDefinition({});
        return;
    }
    emitDefinition({ advanced_search_query: parsed as AdvancedSearchQuery });
}
</script>

<template>
    <div class="field search-rule-form">
        <label for="abac-saved-search">{{
            $gettext("Start from a saved search")
        }}</label>
        <Select
            input-id="abac-saved-search"
            :model-value="selectedSavedSearchId"
            :options="savedSearchGroups"
            option-group-label="label"
            option-group-children="items"
            :loading="isLoadingSavedSearches"
            option-label="label"
            option-value="id"
            option-disabled="disabled"
            :filter="true"
            :placeholder="$gettext('Select a saved search…')"
            :empty-message="$gettext('You have no saved searches')"
            :aria-describedby="SAVED_SEARCH_HELP_ID"
            @update:model-value="onSavedSearchChange"
        />
        <p
            :id="SAVED_SEARCH_HELP_ID"
            class="query-help"
        >
            {{
                $gettext(
                    "Lists your saved searches and those shared with you. Choosing one copies its query into the rule: the rule doesn't follow later changes to the search, and anyone who manages rules can see the query.",
                )
            }}
        </p>
    </div>
    <div class="field search-rule-form">
        <label for="abac-search-query">{{
            $gettext("Advanced Search query")
        }}</label>
        <p
            :id="QUERY_HELP_ID"
            class="query-help"
        >
            {{
                $gettext(
                    "Or, in Advanced Search, build the search, open its Payload tab and paste the query here. The query is checked when you save.",
                )
            }}
        </p>
        <Textarea
            id="abac-search-query"
            rows="12"
            spellcheck="false"
            :model-value="queryText"
            :invalid="Boolean(queryError)"
            :aria-describedby="
                queryError
                    ? `${QUERY_HELP_ID} ${QUERY_ERROR_ID}`
                    : QUERY_HELP_ID
            "
            @update:model-value="onQueryInput"
        />
        <p
            v-if="queryError"
            :id="QUERY_ERROR_ID"
            class="query-error"
            role="alert"
        >
            {{ queryError }}
        </p>
        <p
            v-else-if="definition.advanced_search_query?.graph_slug"
            class="query-help"
        >
            {{
                $gettext("Resource model: %{slug}", {
                    slug: definition.advanced_search_query.graph_slug,
                })
            }}
        </p>
    </div>
</template>

<style scoped>
.search-rule-form :deep(textarea) {
    inline-size: 100%;
    font-family: monospace;
    font-size: 1.15rem;
}

.search-rule-form .query-help {
    margin: 0;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}

.search-rule-form .query-error {
    margin: 0;
    color: var(--p-abac-danger);
}
</style>
