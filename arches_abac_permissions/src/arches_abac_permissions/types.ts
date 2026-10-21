export type PermissionName = "read" | "update" | "delete";

export interface LifecycleStateDefinition {
    graphid: string;
    lifecycle_state_id: string;
}

export interface RuleTypeInfo {
    key: string;
    label: string;
    description: string;
    icon: string;
}

export interface GroupPermission {
    groupid: number;
    permissions: PermissionName[];
}

export interface Rule {
    id: string;
    name: string;
    description: string;
    active: boolean;
    rule_type: string | null;
    definition: Partial<LifecycleStateDefinition>;
    group_permissions: GroupPermission[];
}

export interface Group {
    id: number;
    name: string;
    member_count: number;
}

export interface LifecycleState {
    id: string;
    name: string;
}

export interface ResourceModel {
    graphid: string;
    name: string;
    lifecycle_states: LifecycleState[];
}

// Editable copy of a rule; `id` is null until the rule is saved.
export interface RuleDraft {
    id: string | null;
    rule_type: string;
    name: string;
    description: string;
    active: boolean;
    definition: Partial<LifecycleStateDefinition>;
    grants: Record<number, PermissionName[]>;
}
