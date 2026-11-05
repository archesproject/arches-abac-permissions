export type PermissionName = "read" | "update" | "delete";

// Shape is owned by each rule type (see rule-types/).
export type RuleDefinition = Record<string, unknown>;

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
    rule_type: string;
    definition: RuleDefinition;
    group_permissions: GroupPermission[];
}

export interface Group {
    id: number;
    name: string;
    member_count: number;
    is_built_in: boolean;
    is_public: boolean;
}

// Editable copy of a rule; `id` is null until the rule is saved.
export interface RuleDraft {
    id: string | null;
    rule_type: string;
    name: string;
    description: string;
    active: boolean;
    definition: RuleDefinition;
    grants: Record<number, PermissionName[]>;
}

export interface User {
    id: number;
    username: string;
    first_name: string;
    last_name: string;
    is_active: boolean;
    is_superuser: boolean;
    is_public: boolean;
    groups: number[];
}

export interface UserDetails extends User {
    email: string;
    last_login: string | null;
    date_joined: string;
}
