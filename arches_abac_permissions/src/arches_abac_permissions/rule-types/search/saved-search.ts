import {
    isCompleteQuery,
    isObject,
} from "@/arches_abac_permissions/rule-types/search/query.ts";

import type {
    AdvancedSearchQuery,
    SavedSearch,
} from "@/arches_abac_permissions/rule-types/search/types";

// Copied from arches-search's buildSearchApiRequestBody
// (SimpleSearch/utils/search-payload-builder.ts) and must stay in step with it.
// TODO: once arches-search exports a saved-search-to-query builder, load it
// with a template-string import (`@/${app}/...`, which doesn't break the build
// when arches-search is absent) and remove this copy.
export function getRuleQuery(
    savedSearch: SavedSearch,
): AdvancedSearchQuery | null {
    if (!isObject(savedSearch.query_definition)) {
        return null;
    }
    const { terms, queries, graphSlugs, mapFilter } =
        savedSearch.query_definition;
    if ((terms ?? []).length > 0) {
        return null;
    }
    const graphSlug =
        queries?.advancedQuery?.graph_slug ??
        (graphSlugs?.length === 1 ? graphSlugs[0] : undefined);
    if (!graphSlug) {
        return null;
    }
    const groups = Object.values(queries ?? {}).filter(
        (query) => isObject(query) && query.graph_slug === graphSlug,
    );
    const clauses = mapFilter?.features?.length
        ? [
              {
                  type: "LITERAL",
                  quantifier: "ANY",
                  subject: {
                      type: "SEARCH_MODELS",
                      graph_slug: graphSlug,
                      node_alias: "",
                      search_models: ["GeometrySearch"],
                  },
                  operator: "GEO_INTERSECTS",
                  operands: [{ type: "GEO_LITERAL", value: mapFilter }],
              },
          ]
        : [];
    const ruleQuery =
        clauses.length === 0 && groups.length <= 1
            ? groups[0]
            : {
                  graph_slug: graphSlug,
                  scope: "RESOURCE",
                  logic: "AND",
                  clauses,
                  groups,
                  aggregations: [],
                  relationship: null,
              };
    return isCompleteQuery(ruleQuery) ? ruleQuery : null;
}
