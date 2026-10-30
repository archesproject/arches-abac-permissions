import arches from "arches";
import Cookies from "js-cookie";

import type {
    Account,
    Group,
    Language,
    ListItemOption,
    MapConfig,
    ResourceModel,
    ResourceSet,
    Rule,
    RuleTypeInfo,
    TileNode,
} from "@/arches_abac_permissions/types";

function getToken() {
    const token = Cookies.get("csrftoken");
    if (!token) {
        throw new Error("Missing csrftoken");
    }
    return token;
}

export async function request<T>(
    url: string,
    method = "GET",
    body?: unknown,
): Promise<T> {
    const isRead = method === "GET";
    const response = await fetch(url, {
        method,
        headers: {
            Accept: "application/json",
            ...(isRead ? {} : { "X-CSRFToken": getToken() }),
            ...(body === undefined
                ? {}
                : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 204) {
        return undefined as T;
    }
    let parsed;
    try {
        parsed = await response.json();
    } catch (error) {
        throw new Error(response.statusText, { cause: error });
    }
    if (!response.ok) {
        throw new Error(parsed.message || response.statusText);
    }
    return parsed as T;
}

export const fetchRules = async () =>
    (await request<{ rules: Rule[] }>(arches.urls.abac_rules)).rules;

export const createRule = (payload: unknown) =>
    request<Rule>(arches.urls.abac_rules, "POST", payload);

export const updateRule = (ruleId: string, payload: unknown) =>
    request<Rule>(arches.urls.abac_rule(ruleId), "PUT", payload);

export const deleteRule = (ruleId: string) =>
    request<void>(arches.urls.abac_rule(ruleId), "DELETE");

export const fetchRuleTypes = async () =>
    (await request<{ rule_types: RuleTypeInfo[] }>(arches.urls.abac_rule_types))
        .rule_types;

export const fetchResourceModels = async () =>
    (
        await request<{ resource_models: ResourceModel[] }>(
            arches.urls.abac_resource_models,
        )
    ).resource_models;

export const fetchResourceSets = async () =>
    (
        await request<{ resource_sets: ResourceSet[] }>(
            arches.urls.abac_resource_sets,
        )
    ).resource_sets;

export const fetchResourceModelNodes = async (
    graphid: string,
    datatype?: string,
) => {
    const url = arches.urls.abac_resource_model_nodes(graphid);
    const query = datatype ? `?${new URLSearchParams({ datatype })}` : "";
    return (await request<{ nodes: TileNode[] }>(url + query)).nodes;
};

export const fetchMapConfig = () =>
    request<MapConfig>(arches.urls.abac_map_config);

export const fetchLanguages = async () =>
    (await request<{ languages: Language[] }>(arches.urls.abac_languages))
        .languages;

export const fetchControlledListItems = async (listId: string) =>
    (
        await request<{ items: ListItemOption[] }>(
            arches.urls.abac_controlled_list_items(listId),
        )
    ).items;

export const fetchGroups = async () =>
    (await request<{ groups: Group[] }>(arches.urls.abac_groups)).groups;

export const createGroup = (name: string) =>
    request<Group>(arches.urls.abac_groups, "POST", { name });

export const deleteGroup = (groupId: number) =>
    request<void>(arches.urls.abac_group(groupId), "DELETE");

export const fetchAccounts = async () =>
    (await request<{ users: Account[] }>(arches.urls.abac_users)).users;

export const changeMembership = async (
    userIds: number[],
    add: number[],
    remove: number[],
) =>
    (
        await request<{ users: Account[] }>(
            arches.urls.abac_user_group_membership,
            "POST",
            { user_ids: userIds, add, remove },
        )
    ).users;
