import { defineAsyncComponent } from "vue";

import { isGroupComplete } from "@/arches_abac_permissions/rule-types/combined/group.ts";

import type { CombinedDefinition } from "@/arches_abac_permissions/rule-types/combined/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

export default {
    key: "combined",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/combined/CombinedRuleForm/CombinedRuleForm.vue"
            ),
    ),
    isComplete: isGroupComplete,
} satisfies RuleTypeModule<CombinedDefinition>;
