import { describe, expect, it } from "vitest";

import {
    userDisplayName,
    userMatchesFilter,
    draftFromRule,
    draftToPayload,
    groupHoldings,
    isDraftComplete,
    newDraft,
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
};

const groups: Group[] = [
    { id: 1, name: "A", member_count: 0, is_built_in: false, is_public: false },
    { id: 2, name: "B", member_count: 0, is_built_in: false, is_public: false },
];

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
