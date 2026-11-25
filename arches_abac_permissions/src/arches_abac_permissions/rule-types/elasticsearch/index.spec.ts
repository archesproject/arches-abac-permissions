import { describe, expect, it } from "vitest";

import elasticsearch from "@/arches_abac_permissions/rule-types/elasticsearch/index.ts";

describe("elasticsearch rule type", () => {
    it("needs a search", () => {
        expect(elasticsearch.isComplete({})).toBe(false);
        expect(elasticsearch.isComplete({ query_string: "  " })).toBe(false);
        expect(
            elasticsearch.isComplete({ query_string: "term-filter=x" }),
        ).toBe(true);
    });
});
