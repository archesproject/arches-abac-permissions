import type { FeatureCollection } from "geojson";

// One graph's arches-search advanced search payload; only the keys checked here are typed.
export interface AdvancedSearchQuery {
    graph_slug: string;
    clauses: unknown[];
    groups: AdvancedSearchQuery[];
    [key: string]: unknown;
}

export interface SearchDefinition {
    advanced_search_query: AdvancedSearchQuery;
}

// arches-search's whole saved search state, as Simple and Advanced Search save it.
export interface SavedSearchDefinition {
    terms: unknown[];
    queries: Record<string, AdvancedSearchQuery>;
    graphSlugs: string[];
    mapFilter: FeatureCollection | null;
    [key: string]: unknown;
}

export interface SavedSearch {
    savedsearchid: string;
    name: string;
    description: string;
    query_definition: SavedSearchDefinition;
    creator: { id: number; username: string };
}
