import { defineAsyncComponent } from "vue";

import { isCompleteQuery } from "@/arches_abac_permissions/rule-types/search/query.ts";

import type { SearchDefinition } from "@/arches_abac_permissions/rule-types/search/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

export default {
    key: "search",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/search/SearchRuleForm/SearchRuleForm.vue"
            ),
    ),
    isComplete: (definition) =>
        isCompleteQuery(definition.advanced_search_query),
} satisfies RuleTypeModule<SearchDefinition>;
