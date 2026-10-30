import { defineAsyncComponent } from "vue";

import type { SpatialDefinition } from "@/arches_abac_permissions/rule-types/spatial/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

export default {
    key: "spatial",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/spatial/SpatialRuleForm/SpatialRuleForm.vue"
            ),
    ),
    isComplete: (definition) =>
        Boolean(definition.graphid && definition.nodeid && definition.geometry),
} satisfies RuleTypeModule<SpatialDefinition>;
