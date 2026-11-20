import { describe, expect, it } from "vitest";

import combined from "@/arches_abac_permissions/rule-types/combined/index.ts";
import { toGroup } from "@/arches_abac_permissions/rule-types/combined/group.ts";

describe("combined rule type", () => {
    it("needs an operator and at least one rule or group", () => {
        expect(combined.isComplete({})).toBe(false);
        expect(combined.isComplete({ operator: "or", rule_ids: [] })).toBe(
            false,
        );
        expect(combined.isComplete({ rule_ids: ["a"] })).toBe(false);
        expect(combined.isComplete({ operator: "and", rule_ids: ["a"] })).toBe(
            true,
        );
    });

    it("needs every nested group to be complete", () => {
        const filled = toGroup({ operator: "and", rule_ids: ["a"] });
        const empty = toGroup({ operator: "and" });
        expect(
            combined.isComplete(toGroup({ operator: "or", groups: [filled] })),
        ).toBe(true);
        expect(
            combined.isComplete(
                toGroup({ operator: "or", rule_ids: ["b"], groups: [empty] }),
            ),
        ).toBe(false);
    });
});
