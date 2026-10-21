import { describe, expect, it } from "vitest";

import {
    draftFromRule,
    draftToPayload,
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
    { id: 1, name: "A", member_count: 0 },
    { id: 2, name: "B", member_count: 0 },
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
