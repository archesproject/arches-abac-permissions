<script setup lang="ts">
import { useGettext } from "vue3-gettext";

import Textarea from "openvue/textarea";

import type { ElasticsearchDefinition } from "@/arches_abac_permissions/rule-types/elasticsearch/types";

const { $gettext } = useGettext();

const definition = defineModel<Partial<ElasticsearchDefinition>>({
    required: true,
});

function onQueryChange(queryString: string | undefined): void {
    definition.value = { query_string: queryString ?? "" };
}
</script>

<template>
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
                "Uses the search's filters. Paging and sorting are ignored.",
            )
        }}</small>
    </div>
</template>
