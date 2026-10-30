import type { MultiPolygon, Polygon } from "geojson";

export type PermissionName = "read" | "update" | "delete";

export interface LifecycleStateDefinition {
    graphid: string;
    lifecycle_state_id: string;
}

export interface ResourceSetDefinition {
    resource_set_id: string;
}

export interface TileNodeValueDefinition {
    graphid: string;
    nodeid: string;
    value: string;
    language: string;
}

export type AreaGeometry = Polygon | MultiPolygon;

export interface SpatialDefinition {
    graphid: string;
    nodeid: string;
    // EPSG:4326
    geometry: AreaGeometry;
}

export type RuleDefinition = Partial<
    LifecycleStateDefinition &
        ResourceSetDefinition &
        TileNodeValueDefinition &
        SpatialDefinition
>;

export interface NodeOption {
    id: string;
    label: string;
}

export interface TileNode {
    nodeid: string;
    name: string;
    alias: string;
    datatype: string;
    options?: NodeOption[];
    true_label?: string;
    false_label?: string;
    date_format?: string;
    controlled_list_id?: string | null;
}

export interface Basemap {
    id: string;
    name: string;
    is_default: boolean;
    layers: Record<string, unknown>[];
    sources: Record<string, Record<string, unknown>>;
}

export interface MapConfig {
    basemaps: Basemap[];
    // [west, south, east, north]
    bounds: [number, number, number, number] | null;
    min_zoom: number;
    max_zoom: number;
    sprite: string;
    glyphs: string;
}

export interface Language {
    code: string;
    name: string;
}

export interface ListItemOption {
    id: string;
    label: string;
    depth: number;
}

export interface ResourceSet {
    id: string;
    name: string;
}

export interface RuleTypeInfo {
    key: string;
    label: string;
    description: string;
    icon: string;
}

export interface GroupPermission {
    groupid: number;
    permissions: PermissionName[];
}

export interface Rule {
    id: string;
    name: string;
    description: string;
    active: boolean;
    rule_type: string | null;
    definition: RuleDefinition;
    group_permissions: GroupPermission[];
    // SQL for an index that speeds up evaluating the rule, if one helps.
    index_sql: string | null;
}

export interface Group {
    id: number;
    name: string;
    member_count: number;
}

export interface LifecycleState {
    id: string;
    name: string;
}

export interface ResourceModel {
    graphid: string;
    name: string;
    lifecycle_states: LifecycleState[];
}

// Editable copy of a rule; `id` is null until the rule is saved.
export interface RuleDraft {
    id: string | null;
    rule_type: string;
    name: string;
    description: string;
    active: boolean;
    definition: RuleDefinition;
    grants: Record<number, PermissionName[]>;
}

export interface Account {
    id: number;
    username: string;
    first_name: string;
    last_name: string;
    email: string;
    is_active: boolean;
    is_superuser: boolean;
    last_login: string | null;
    date_joined: string;
    groups: number[];
}
