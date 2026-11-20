import type {
    CombinedGroup,
    CombinedOperator,
} from "@/arches_abac_permissions/rule-types/combined/types";

export const DEFAULT_OPERATOR: CombinedOperator = "or";

export function toGroup(definition: Partial<CombinedGroup>): CombinedGroup {
    return {
        operator: definition.operator ?? DEFAULT_OPERATOR,
        rule_ids: definition.rule_ids ?? [],
        groups: definition.groups ?? [],
        exclude_rule_ids: definition.exclude_rule_ids ?? [],
    };
}

export function isGroupComplete(group: Partial<CombinedGroup>): boolean {
    const groups = group.groups ?? [];
    return (
        Boolean(group.operator) &&
        Boolean(group.rule_ids?.length || groups.length) &&
        groups.every(isGroupComplete)
    );
}
