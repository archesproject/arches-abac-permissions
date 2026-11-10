import { defineAsyncComponent } from "vue";

import { needsBuffer } from "@/arches_abac_permissions/rule-types/spatial/geometry.ts";
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
        Boolean(
            definition.graphid && definition.nodeid && definition.geometry,
        ) &&
        (!needsBuffer(definition.geometry) || (definition.buffer ?? 0) > 0),
} satisfies RuleTypeModule<SpatialDefinition>;
