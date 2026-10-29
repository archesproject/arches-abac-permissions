import {
    PERMISSION_NAMES,
    RESOURCE_SET,
} from "@/arches_abac_permissions/constants.ts";

import type {
    Account,
    Group,
    PermissionName,
    Rule,
    RuleDraft,
} from "@/arches_abac_permissions/types";

export function newDraft(ruleType: string): RuleDraft {
    return {
        id: null,
        rule_type: ruleType,
        name: "",
        description: "",
        active: true,
        definition: {},
        grants: {},
    };
}

export function draftFromRule(rule: Rule): RuleDraft {
    const grants: Record<number, PermissionName[]> = {};
    for (const grant of rule.group_permissions) {
        grants[grant.groupid] = normalizePermissions(grant.permissions);
    }
    return {
        id: rule.id,
        rule_type: rule.rule_type ?? "",
        name: rule.name,
        description: rule.description,
        active: rule.active,
        definition: { ...rule.definition },
        grants,
    };
}

export function draftToPayload(draft: RuleDraft) {
    return {
        name: draft.name.trim(),
        description: draft.description,
        active: draft.active,
        rule_type: draft.rule_type,
        definition: draft.definition,
        group_permissions: Object.entries(draft.grants)
            .filter(([, permissions]) => permissions.length > 0)
            .map(([groupid, permissions]) => ({
                groupid: Number(groupid),
                permissions: normalizePermissions(permissions),
            })),
    };
}

// Canonical form used to compare a draft with its saved state.
export function serializeDraft(draft: RuleDraft): string {
    const payload = draftToPayload(draft);
    payload.group_permissions.sort((a, b) => a.groupid - b.groupid);
    return JSON.stringify({ ...payload, id: draft.id });
}

export function normalizePermissions(
    permissions: PermissionName[],
): PermissionName[] {
    return PERMISSION_NAMES.filter((name) => permissions.includes(name));
}

export function hasPermission(
    draft: RuleDraft,
    groupId: number,
    permission: PermissionName,
): boolean {
    return (draft.grants[groupId] ?? []).includes(permission);
}

export function setPermission(
    draft: RuleDraft,
    groupId: number,
    permission: PermissionName,
    granted: boolean,
): void {
    const current = new Set(draft.grants[groupId] ?? []);
    if (granted) {
        current.add(permission);
    } else {
        current.delete(permission);
    }
    draft.grants[groupId] = normalizePermissions([...current]);
}

export function setGroupPermissions(
    draft: RuleDraft,
    groupId: number,
    permissions: PermissionName[],
): void {
    draft.grants[groupId] = normalizePermissions(permissions);
}

export function setPermissionForAllGroups(
    draft: RuleDraft,
    groups: Group[],
    permission: PermissionName,
    granted: boolean,
): void {
    for (const group of groups) {
        setPermission(draft, group.id, permission, granted);
    }
}

export function groupNamesForRule(
    rule: Rule,
    groupsById: Map<number, Group>,
): string[] {
    return rule.group_permissions
        .filter((grant) => grant.permissions.length > 0)
        .map((grant) => groupsById.get(grant.groupid)?.name)
        .filter((name): name is string => Boolean(name))
        .sort((a, b) => a.localeCompare(b));
}

export function ruleMatchesFilter(
    rule: Rule,
    filter: string,
    typeLabel: string,
    groupNames: string[],
): boolean {
    const needle = filter.trim().toLowerCase();
    if (!needle) {
        return true;
    }
    return [rule.name, typeLabel, ...groupNames].some((text) =>
        text.toLowerCase().includes(needle),
    );
}

export function isDraftComplete(draft: RuleDraft): boolean {
    if (!draft.name.trim()) {
        return false;
    }
    if (draft.rule_type === RESOURCE_SET) {
        return Boolean(draft.definition.resource_set_id);
    }
    return Boolean(
        draft.definition.graphid && draft.definition.lifecycle_state_id,
    );
}

export function accountDisplayName(account: Account): string {
    const name = `${account.first_name} ${account.last_name}`.trim();
    return name || account.username;
}

export function accountMatchesFilter(
    account: Account,
    filter: string,
    groupNames: string[],
): boolean {
    const query = filter.trim().toLowerCase();
    if (!query) {
        return true;
    }
    return [
        account.username,
        account.first_name,
        account.last_name,
        account.email,
        ...groupNames,
    ].some((value) => value.toLowerCase().includes(query));
}

// Groups held by some or all of `accounts`, with how many hold each.
export function groupHoldings(
    accounts: Account[],
): { groupId: number; count: number }[] {
    const counts = new Map<number, number>();
    for (const account of accounts) {
        for (const groupId of account.groups) {
            counts.set(groupId, (counts.get(groupId) ?? 0) + 1);
        }
    }
    return [...counts].map(([groupId, count]) => ({ groupId, count }));
}
