import { defineAsyncComponent } from "vue";

import type { ResourceSetDefinition } from "@/arches_abac_permissions/rule_types/resource_set/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule_types/types";

export default {
    key: "resource_set",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule_types/resource_set/ResourceSetRuleForm.vue"
            ),
    ),
    isComplete: (definition) => Boolean(definition.resource_set_id),
} satisfies RuleTypeModule<ResourceSetDefinition>;
