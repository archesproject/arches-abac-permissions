import { defineAsyncComponent } from "vue";

import type { TileNodeValueDefinition } from "@/arches_abac_permissions/rule-types/tile-node-value/types";
import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

export default {
    key: "tile_node_value",
    form: defineAsyncComponent(
        () =>
            import(
                "@/arches_abac_permissions/rule-types/tile-node-value/TileNodeValueRuleForm/TileNodeValueRuleForm.vue"
            ),
    ),
    isComplete: (definition) =>
        Boolean(
            definition.graphid && definition.nodeid && definition.value?.trim(),
        ),
} satisfies RuleTypeModule<TileNodeValueDefinition>;
