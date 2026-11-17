import { describe, expect, it } from "vitest";

import { getRuleQuery } from "@/arches_abac_permissions/rule-types/search/saved-search.ts";

import type { FeatureCollection } from "geojson";
import type {
    AdvancedSearchQuery,
    SavedSearch,
    SavedSearchDefinition,
} from "@/arches_abac_permissions/rule-types/search/types";

const QUERY: AdvancedSearchQuery = {
    graph_slug: "monument",
    clauses: [{ type: "LITERAL" }],
    groups: [],
};

const TIME_FILTER: AdvancedSearchQuery = {
    graph_slug: "monument",
    clauses: [{ type: "LITERAL", operator: "BETWEEN" }],
    groups: [],
};

const AREA: FeatureCollection = {
    type: "FeatureCollection",
    features: [
        {
            type: "Feature",
            properties: {},
            geometry: {
                type: "Polygon",
                coordinates: [
                    [
                        [0, 0],
                        [1, 0],
                        [1, 1],
                        [0, 0],
                    ],
                ],
            },
        },
    ],
};

const AREA_CLAUSE = {
    type: "LITERAL",
    quantifier: "ANY",
    subject: {
        type: "SEARCH_MODELS",
        graph_slug: "monument",
        node_alias: "",
        search_models: ["GeometrySearch"],
    },
    operator: "GEO_INTERSECTS",
    operands: [{ type: "GEO_LITERAL", value: AREA }],
};

function savedSearch(overrides: Partial<SavedSearchDefinition>): SavedSearch {
    return {
        savedsearchid: "s1",
        name: "Monuments",
        description: "",
        creator: { id: 1, username: "admin" },
        query_definition: {
            terms: [],
            queries: { advancedQuery: QUERY },
            graphSlugs: ["monument"],
            mapFilter: null,
            sort: [],
            includeRelated: false,
            ...overrides,
        },
    };
}

function combined(
    clauses: unknown[],
    groups: AdvancedSearchQuery[],
): AdvancedSearchQuery {
    return {
        graph_slug: "monument",
        scope: "RESOURCE",
        logic: "AND",
        clauses,
        groups,
        aggregations: [],
        relationship: null,
    };
}

describe("getRuleQuery", () => {
    it("returns an advanced search's query unchanged", () => {
        expect(getRuleQuery(savedSearch({}))).toEqual(QUERY);
    });

    it("ANDs the drawn area with the advanced query", () => {
        expect(getRuleQuery(savedSearch({ mapFilter: AREA }))).toEqual(
            combined([AREA_CLAUSE], [QUERY]),
        );
    });

    it("uses the drawn area alone when there is no query", () => {
        expect(
            getRuleQuery(savedSearch({ queries: {}, mapFilter: AREA })),
        ).toEqual(combined([AREA_CLAUSE], []));
    });

    it("ANDs other saved filters for the same model", () => {
        expect(
            getRuleQuery(
                savedSearch({
                    queries: { advancedQuery: QUERY, timeFilter: TIME_FILTER },
                }),
            ),
        ).toEqual(combined([], [QUERY, TIME_FILTER]));
    });

    it("rejects searches with free-text terms", () => {
        expect(getRuleQuery(savedSearch({ terms: [{ id: "t" }] }))).toBeNull();
    });

    it("rejects searches with nothing to match on", () => {
        expect(getRuleQuery(savedSearch({ queries: {} }))).toBeNull();
        expect(
            getRuleQuery(
                savedSearch({
                    queries: {},
                    mapFilter: AREA,
                    graphSlugs: ["monument", "place"],
                }),
            ),
        ).toBeNull();
    });

    it("rejects malformed saved searches", () => {
        const noDefinition = {
            ...savedSearch({}),
            query_definition: null,
        } as unknown as SavedSearch;
        expect(getRuleQuery(noDefinition)).toBeNull();
        const nullQuery = savedSearch({
            queries: { advancedQuery: null },
        } as unknown as Partial<SavedSearchDefinition>);
        expect(getRuleQuery(nullQuery)).toBeNull();
    });

    it("rejects a saved query with no clauses", () => {
        const empty = { ...QUERY, clauses: [] };
        expect(
            getRuleQuery(savedSearch({ queries: { advancedQuery: empty } })),
        ).toBeNull();
    });
});
