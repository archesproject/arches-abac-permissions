import { defineAsyncComponent } from "vue";

import type { LifecycleStateDefinition } from "@/arches_abac_permissions/rule_types/lifecycle_state/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule_types/types";

export default {
    key: "lifecycle_state",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule_types/lifecycle_state/LifecycleStateRuleForm.vue"
            ),
    ),
    isComplete: (definition) =>
        Boolean(definition.graphid && definition.lifecycle_state_id),
} satisfies RuleTypeModule<LifecycleStateDefinition>;
