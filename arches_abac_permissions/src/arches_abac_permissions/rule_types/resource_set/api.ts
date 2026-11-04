import arches from "arches";

import { request } from "@/arches_abac_permissions/api.ts";

import type { ResourceSet } from "@/arches_abac_permissions/rule_types/resource_set/types";

export const fetchResourceSets = async () =>
    (
        await request<{ resource_sets: ResourceSet[] }>(
            arches.urls.abac_resource_sets,
        )
    ).resource_sets;
