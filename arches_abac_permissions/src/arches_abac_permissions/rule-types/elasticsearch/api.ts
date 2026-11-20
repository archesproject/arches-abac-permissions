import arches from "arches";

import { request } from "@/arches_abac_permissions/api.ts";

import type { SavedSearch } from "@/arches_abac_permissions/rule-types/elasticsearch/types";

export const fetchSavedSearches = async () =>
    (
        await request<{ saved_searches: SavedSearch[] }>(
            arches.urls.abac_saved_searches,
        )
    ).saved_searches;
