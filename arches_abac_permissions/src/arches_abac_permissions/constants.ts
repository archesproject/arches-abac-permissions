import type { PermissionName } from "@/arches_abac_permissions/types";

export const ERROR = "error";
export const SUCCESS = "success";
export const DEFAULT_ERROR_TOAST_LIFE = 8000;
export const DEFAULT_SUCCESS_TOAST_LIFE = 3000;

export const LIFECYCLE_STATE = "lifecycle_state";
export const RESOURCE_SET = "resource_set";
export const TILE_NODE_VALUE = "tile_node_value";
export const SPATIAL = "spatial";
export const GEOMETRY_DATATYPE = "geojson-feature-collection";

export const PERMISSION_NAMES: PermissionName[] = ["read", "update", "delete"];
