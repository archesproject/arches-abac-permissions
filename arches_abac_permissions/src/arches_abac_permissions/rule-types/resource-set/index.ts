import { defineAsyncComponent } from "vue";

import type { ResourceSetDefinition } from "@/arches_abac_permissions/rule-types/resource-set/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

export default {
    key: "resource_set",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/resource-set/ResourceSetRuleForm/ResourceSetRuleForm.vue"
            ),
    ),
    isComplete: (definition) => Boolean(definition.resource_set_id),
} satisfies RuleTypeModule<ResourceSetDefinition>;
