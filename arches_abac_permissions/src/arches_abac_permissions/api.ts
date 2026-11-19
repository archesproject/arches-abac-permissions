import arches from "arches";
import Cookies from "js-cookie";

import type {
    Group,
    NewUserFieldErrors,
    NewUserPayload,
    Rule,
    RuleTypeInfo,
    User,
    UserDetails,
    UserDirectory,
    UserUpdatePayload,
} from "@/arches_abac_permissions/types";

export class ApiError extends Error {
    fieldErrors: NewUserFieldErrors;
    code?: string;

    constructor(
        message: string,
        fieldErrors: NewUserFieldErrors = {},
        code?: string,
    ) {
        super(message);
        this.fieldErrors = fieldErrors;
        this.code = code;
    }
}

function getToken(): string {
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
        throw new ApiError(
            parsed.message || response.statusText,
            parsed.errors,
            parsed.code,
        );
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

export const fetchGroups = async () =>
    (await request<{ groups: Group[] }>(arches.urls.abac_groups)).groups;

export const createGroup = (name: string) =>
    request<Group>(arches.urls.abac_groups, "POST", { name });

export const deleteGroup = (groupId: number) =>
    request<void>(arches.urls.abac_group(groupId), "DELETE");

export const fetchUsers = () => request<UserDirectory>(arches.urls.abac_users);

export const createUser = (payload: NewUserPayload) =>
    request<User>(arches.urls.abac_users, "POST", payload);

export const updateUser = (userId: number, payload: UserUpdatePayload) =>
    request<UserDetails>(arches.urls.abac_user(userId), "PATCH", payload);

export const deleteUser = (userId: number) =>
    request<void>(arches.urls.abac_user(userId), "DELETE");

export const fetchUserDetails = (userId: number) =>
    request<UserDetails>(arches.urls.abac_user(userId));

export const changeMembership = async (
    userIds: number[],
    add: number[],
    remove: number[],
) =>
    (
        await request<{ users: User[] }>(
            arches.urls.abac_user_group_membership,
            "POST",
            { user_ids: userIds, add, remove },
        )
    ).users;
