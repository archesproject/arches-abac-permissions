import arches from "arches";

import { request } from "@/arches_abac_permissions/api.ts";

import type {
    GeometryNode,
    MapConfig,
    ResourceModel,
} from "@/arches_abac_permissions/rule-types/spatial/types";

const GEOMETRY_DATATYPE = "geojson-feature-collection";

export const fetchResourceModels = async (): Promise<ResourceModel[]> =>
    (
        await request<{ resource_models: ResourceModel[] }>(
            arches.urls.abac_resource_models,
        )
    ).resource_models;

export const fetchGeometryNodes = async (
    graphid: string,
): Promise<GeometryNode[]> => {
    const query = new URLSearchParams({ datatype: GEOMETRY_DATATYPE });
    return (
        await request<{ nodes: GeometryNode[] }>(
            `${arches.urls.abac_resource_model_nodes(graphid)}?${query}`,
        )
    ).nodes;
};

export const fetchMapConfig = (): Promise<MapConfig> =>
    request<MapConfig>(arches.urls.abac_map_config);
