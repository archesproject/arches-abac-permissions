import arches from "arches";

import { request } from "@/arches_abac_permissions/api.ts";

import type {
    Language,
    ListItemOption,
    ResourceModel,
    TileNode,
} from "@/arches_abac_permissions/rule-types/tile-node-value/types";

export const fetchResourceModels = async (): Promise<ResourceModel[]> =>
    (
        await request<{ resource_models: ResourceModel[] }>(
            arches.urls.abac_resource_models,
        )
    ).resource_models;

export const fetchResourceModelNodes = async (
    graphid: string,
): Promise<TileNode[]> =>
    (
        await request<{ nodes: TileNode[] }>(
            arches.urls.abac_resource_model_nodes(graphid),
        )
    ).nodes;

export const fetchLanguages = async (): Promise<Language[]> =>
    (await request<{ languages: Language[] }>(arches.urls.abac_languages))
        .languages;

export const fetchControlledListItems = async (
    listId: string,
): Promise<ListItemOption[]> =>
    (
        await request<{ items: ListItemOption[] }>(
            arches.urls.abac_controlled_list_items(listId),
        )
    ).items;
