import { defineAsyncComponent } from "vue";

import type {
    AdvancedSearchQuery,
    SearchDefinition,
} from "@/arches_abac_permissions/rule-types/search/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

// Mirrors the server: a query with no clauses at any depth would match the whole graph.
function hasClause(query: AdvancedSearchQuery): boolean {
    if (Array.isArray(query.clauses) && query.clauses.length > 0) {
        return true;
    }
    return Array.isArray(query.groups) && query.groups.some(hasClause);
}

export default {
    key: "search",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/search/SearchRuleForm/SearchRuleForm.vue"
            ),
    ),
    isComplete: (definition) => {
        const query = definition.advanced_search_query;
        return (
            query !== undefined && Boolean(query.graph_slug) && hasClause(query)
        );
    },
} satisfies RuleTypeModule<SearchDefinition>;
