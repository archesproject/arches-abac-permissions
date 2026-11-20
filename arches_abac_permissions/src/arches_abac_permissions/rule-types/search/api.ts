import { generateArchesURL } from "@/arches_vue_components/application";

import { request } from "@/arches_abac_permissions/api.ts";

import type { SavedSearch } from "@/arches_abac_permissions/rule-types/search/types";

const SAVED_SEARCHES_URL_NAME = "arches_search:saved_searches";

function fetchSavedSearchScope(
    scope: "mine" | "shared",
): Promise<SavedSearch[]> {
    return request<SavedSearch[]>(
        generateArchesURL(SAVED_SEARCHES_URL_NAME, {}, { scope }),
    );
}

// arches-search's own API, so the user sees the same searches they see there.
export async function fetchSavedSearches(): Promise<{
    mine: SavedSearch[];
    shared: SavedSearch[];
}> {
    const [mine, shared] = await Promise.all([
        fetchSavedSearchScope("mine"),
        fetchSavedSearchScope("shared"),
    ]);
    return { mine, shared };
}
