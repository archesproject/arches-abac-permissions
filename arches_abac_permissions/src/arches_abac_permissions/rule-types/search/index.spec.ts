import { describe, expect, it } from "vitest";

import search from "@/arches_abac_permissions/rule-types/search/index.ts";

import type { AdvancedSearchQuery } from "@/arches_abac_permissions/rule-types/search/types";

function query(overrides: Partial<AdvancedSearchQuery>): AdvancedSearchQuery {
    return { graph_slug: "monument", clauses: [], groups: [], ...overrides };
}

describe("search rule completeness", () => {
    it("requires a query", () => {
        expect(search.isComplete({})).toBe(false);
    });

    it("requires a graph slug", () => {
        expect(
            search.isComplete({
                advanced_search_query: query({ graph_slug: "", clauses: [{}] }),
            }),
        ).toBe(false);
    });

    it("requires a clause at some depth", () => {
        expect(search.isComplete({ advanced_search_query: query({}) })).toBe(
            false,
        );
        expect(
            search.isComplete({
                advanced_search_query: query({ clauses: [{}] }),
            }),
        ).toBe(true);
        expect(
            search.isComplete({
                advanced_search_query: query({
                    groups: [query({ clauses: [{}] })],
                }),
            }),
        ).toBe(true);
    });

    it("treats groups that aren't objects as having no clauses", () => {
        const groups = [null] as unknown as AdvancedSearchQuery[];
        expect(
            search.isComplete({ advanced_search_query: query({ groups }) }),
        ).toBe(false);
    });
});
