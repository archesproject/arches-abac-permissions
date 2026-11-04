import lifecycleState from "@/arches_abac_permissions/rule_types/lifecycle_state/index.ts";
import resourceSet from "@/arches_abac_permissions/rule_types/resource_set/index.ts";

import type { RuleTypeModule } from "@/arches_abac_permissions/rule_types/types";

// Register new rule types here.
const RULE_TYPE_MODULES: RuleTypeModule[] = [lifecycleState, resourceSet];

export function getRuleTypeForKey(key: string | null | undefined) {
    return RULE_TYPE_MODULES.find((module) => module.key === key);
}
