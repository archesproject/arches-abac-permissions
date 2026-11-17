import type { AdvancedSearchQuery } from "@/arches_abac_permissions/rule-types/search/types";

// Pasted and shared queries are untrusted JSON, so shapes are checked, not assumed.
export function isObject(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Mirrors the server: a query with no clauses at any depth would match the whole graph.
function hasClause(group: unknown): boolean {
    if (!isObject(group)) {
        return false;
    }
    if (Array.isArray(group.clauses) && group.clauses.length > 0) {
        return true;
    }
    return Array.isArray(group.groups) && group.groups.some(hasClause);
}

export function isCompleteQuery(query: unknown): query is AdvancedSearchQuery {
    return isObject(query) && Boolean(query.graph_slug) && hasClause(query);
}
