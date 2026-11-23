import { describe, expect, it } from "vitest";

import {
    userDisplayName,
    userMatchesFilter,
    draftFromRule,
    draftToPayload,
    grantsBecomePublic,
    groupHoldings,
    inheritedGrants,
    nestedGroupIds,
    isDraftComplete,
    newDraft,
    sameDefinition,
    ruleMatchesFilter,
    serializeDraft,
    setGroupPermissions,
    setPermission,
    setPermissionForAllGroups,
} from "@/arches_abac_permissions/utils.ts";

import type { Group, Rule } from "@/arches_abac_permissions/types";

const rule: Rule = {
    id: "rule-1",
    name: "Active people",
    description: "",
    active: true,
    rule_type: "lifecycle_state",
    definition: { graphid: "g", lifecycle_state_id: "s" },
    group_permissions: [{ groupid: 2, permissions: ["delete", "read"] }],
    index_sql: null,
};

function group(id: number, name: string, extra: Partial<Group> = {}): Group {
    return {
        id,
        name,
        member_count: 0,
        is_built_in: false,
        is_public: false,
        parent_ids: [],
        inherits_from_ids: [],
        ...extra,
    };
}

const groups: Group[] = [group(1, "A"), group(2, "B")];

describe("drafts", () => {
    it("normalizes permission order when loading a rule", () => {
        expect(draftFromRule(rule).grants).toEqual({ 2: ["read", "delete"] });
    });

    it("is unchanged by a round trip", () => {
        const draft = draftFromRule(rule);
        expect(serializeDraft(draft)).toBe(serializeDraft(draftFromRule(rule)));
    });

    it("omits groups without permissions from the payload", () => {
        const draft = draftFromRule(rule);
        setGroupPermissions(draft, 1, []);
        expect(draftToPayload(draft).group_permissions).toEqual([
            { groupid: 2, permissions: ["read", "delete"] },
        ]);
    });

    it("detects changes", () => {
        const draft = draftFromRule(rule);
        const before = serializeDraft(draft);
        setPermission(draft, 1, "update", true);
        expect(serializeDraft(draft)).not.toBe(before);
        setPermission(draft, 1, "update", false);
        expect(serializeDraft(draft)).toBe(before);
    });

    it("requires a name and a complete definition", () => {
        const draft = newDraft("lifecycle_state");
        expect(isDraftComplete(draft)).toBe(false);
        draft.name = "Name";
        draft.definition = { graphid: "g", lifecycle_state_id: "s" };
        expect(isDraftComplete(draft)).toBe(true);
    });

    it("requires a model, node and value for tile node value rules", () => {
        const draft = newDraft("tile_node_value");
        draft.name = "Name";
        draft.definition = { graphid: "g", nodeid: "n", value: "  " };
        expect(isDraftComplete(draft)).toBe(false);
        draft.definition.value = "x";
        expect(isDraftComplete(draft)).toBe(true);
        draft.definition.nodeid = undefined;
        expect(isDraftComplete(draft)).toBe(false);
    });

    it("compares definitions ignoring key order and empty values", () => {
        expect(
            sameDefinition(
                { graphid: "g", nodeid: "n", language: "" },
                { nodeid: "n", graphid: "g" },
            ),
        ).toBe(true);
        expect(sameDefinition({ value: "a" }, { value: "b" })).toBe(false);
    });
});

describe("permission helpers", () => {
    it("grants and revokes a permission for every group", () => {
        const draft = newDraft("lifecycle_state");
        setPermissionForAllGroups(draft, groups, "read", true);
        expect(draft.grants).toEqual({ 1: ["read"], 2: ["read"] });
        setPermissionForAllGroups(draft, groups, "read", false);
        expect(draft.grants).toEqual({ 1: [], 2: [] });
    });
});

describe("ruleMatchesFilter", () => {
    it("matches name, type, and group names case-insensitively", () => {
        expect(ruleMatchesFilter(rule, "PEOPLE", "Type", [])).toBe(true);
        expect(ruleMatchesFilter(rule, "lifecycle", "Lifecycle", [])).toBe(
            true,
        );
        expect(ruleMatchesFilter(rule, "editors", "Type", ["Editors"])).toBe(
            true,
        );
        expect(ruleMatchesFilter(rule, "zzz", "Type", ["Editors"])).toBe(false);
        expect(ruleMatchesFilter(rule, "  ", "Type", [])).toBe(true);
    });
});

describe("isDraftComplete for resource set rules", () => {
    it("requires a resource set id", () => {
        const draft = newDraft("resource_set");
        draft.name = "Set rule";
        expect(isDraftComplete(draft)).toBe(false);
        draft.definition = { resource_set_id: "s" };
        expect(isDraftComplete(draft)).toBe(true);
    });
});

describe("user helpers", () => {
    const user = (id: number, groups: number[]) => ({
        id,
        username: `u${id}`,
        first_name: "Ada",
        last_name: "Lovelace",
        is_active: true,
        is_superuser: false,
        is_public: false,
        groups,
    });

    it("counts group holdings", () => {
        expect(groupHoldings([user(1, [1, 2]), user(2, [2])])).toEqual([
            { groupId: 1, count: 1 },
            { groupId: 2, count: 2 },
        ]);
    });

    it("filters by name and group", () => {
        const a = user(1, []);
        expect(userMatchesFilter(a, "lovel", [])).toBe(true);
        expect(userMatchesFilter(a, "editors", ["Editors"])).toBe(true);
        expect(userMatchesFilter(a, "zzz", [])).toBe(false);
        expect(userDisplayName({ ...a, first_name: "", last_name: "" })).toBe(
            "u1",
        );
    });
});

describe("inheritedGrants", () => {
    const nested = [
        group(1, "Inner", { inherits_from_ids: [2] }),
        group(2, "Outer"),
    ];

    it("lists grants from the groups a group inherits from", () => {
        expect(inheritedGrants(draftFromRule(rule), nested, 1)).toEqual([
            { via: nested[1], permissions: ["read", "delete"] },
        ]);
    });

    it("is empty without inheritance or grants", () => {
        expect(inheritedGrants(draftFromRule(rule), nested, 2)).toEqual([]);
        const ungranted = draftFromRule({ ...rule, group_permissions: [] });
        expect(inheritedGrants(ungranted, nested, 1)).toEqual([]);
    });
});

describe("nested group helpers", () => {
    const nested = [
        group(1, "Guest", { is_public: true, inherits_from_ids: [2, 3] }),
        group(2, "Staff", { parent_ids: [1] }),
        group(3, "Team", { parent_ids: [2] }),
        group(4, "Other"),
    ];

    it("finds grants that reach a public group through nesting", () => {
        expect(grantsBecomePublic(nested, 1)).toBe(true);
        expect(grantsBecomePublic(nested, 3)).toBe(true);
        expect(grantsBecomePublic(nested, 4)).toBe(false);
    });

    it("lists the groups inside a group at any depth", () => {
        expect(nestedGroupIds(nested, 1)).toEqual(new Set([2, 3]));
        expect(nestedGroupIds(nested, 3)).toEqual(new Set());
    });
});
