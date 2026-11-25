import { defineAsyncComponent } from "vue";

import type { ElasticsearchDefinition } from "@/arches_abac_permissions/rule-types/elasticsearch/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

export default {
    key: "elasticsearch",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/elasticsearch/ElasticsearchRuleForm/ElasticsearchRuleForm.vue"
            ),
    ),
    isComplete: (definition) => Boolean(definition.query_string?.trim()),
} satisfies RuleTypeModule<ElasticsearchDefinition>;
