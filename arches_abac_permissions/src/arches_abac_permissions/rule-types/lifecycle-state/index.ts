import { defineAsyncComponent } from "vue";

import type { LifecycleStateDefinition } from "@/arches_abac_permissions/rule-types/lifecycle-state/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

export default {
    key: "lifecycle_state",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/lifecycle-state/LifecycleStateRuleForm/LifecycleStateRuleForm.vue"
            ),
    ),
    isComplete: (definition) =>
        Boolean(definition.graphid && definition.lifecycle_state_id),
} satisfies RuleTypeModule<LifecycleStateDefinition>;
