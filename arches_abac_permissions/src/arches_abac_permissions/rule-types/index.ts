import lifecycleState from "@/arches_abac_permissions/rule-types/lifecycle-state/index.ts";
import resourceSet from "@/arches_abac_permissions/rule-types/resource-set/index.ts";

import type { RuleTypeModule } from "@/arches_abac_permissions/rule-types/types";

// Register new rule types here.
const RULE_TYPE_MODULES: RuleTypeModule[] = [lifecycleState, resourceSet];

export function getRuleTypeForKey(key: string | null | undefined) {
    return RULE_TYPE_MODULES.find((module) => module.key === key);
}
