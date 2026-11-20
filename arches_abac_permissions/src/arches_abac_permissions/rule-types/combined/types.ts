export type CombinedOperator = "and" | "or";

export interface CombinedGroup {
    operator: CombinedOperator;
    rule_ids: string[];
    groups: CombinedGroup[];
    exclude_rule_ids: string[];
}

export type CombinedDefinition = CombinedGroup;

export interface RuleOption {
    id: string;
    label: string;
}
