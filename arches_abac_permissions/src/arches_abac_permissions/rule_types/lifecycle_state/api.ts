import arches from "arches";

import { request } from "@/arches_abac_permissions/api.ts";

import type { ResourceModel } from "@/arches_abac_permissions/rule_types/lifecycle_state/types";

export const fetchResourceModels = async () =>
    (
        await request<{ resource_models: ResourceModel[] }>(
            arches.urls.abac_resource_models,
        )
    ).resource_models;
