<script setup lang="ts">
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Checkbox from "openvue/checkbox";
import ToggleSwitch from "openvue/toggleswitch";

import { PERMISSION_NAMES } from "@/arches_abac_permissions/constants.ts";
import {
    hasPermission,
    setGroupPermissions,
    setPermission,
    setPermissionForAllGroups,
} from "@/arches_abac_permissions/utils.ts";

import type {
    Group,
    PermissionName,
    RuleDraft,
} from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

const props = defineProps<{
    groups: Group[];
    canSave: boolean;
    isDirty: boolean;
    isSaving: boolean;
}>();
const draft = defineModel<RuleDraft | null>({ required: true });
const emit = defineEmits<{
    (e: "save"): void;
    (e: "cancel"): void;
    (e: "add-group"): void;
    (e: "delete-group", group: Group): void;
}>();

function permissionLabel(permission: PermissionName) {
    return {
        read: $gettext("Read"),
        update: $gettext("Update"),
        delete: $gettext("Delete"),
    }[permission];
}

function allGranted(permission: PermissionName) {
    const current = draft.value;
    return (
        !!current &&
        props.groups.length > 0 &&
        props.groups.every((group) =>
            hasPermission(current, group.id, permission),
        )
    );
}

function toggleAll(permission: PermissionName) {
    if (draft.value) {
        setPermissionForAllGroups(
            draft.value,
            props.groups,
            permission,
            !allGranted(permission),
        );
    }
}

function hasAny(groupId: number) {
    return (draft.value?.grants[groupId] ?? []).length > 0;
}

function toggleGroup(groupId: number) {
    if (draft.value) {
        setGroupPermissions(
            draft.value,
            groupId,
            hasAny(groupId) ? [] : PERMISSION_NAMES,
        );
    }
}
</script>

<template>
    <section
        class="column"
        :aria-label="$gettext('Assign Group Permissions to Rule')"
    >
        <header class="column-header">
            <h2 class="column-title">
                <i
                    class="pi pi-users"
                    aria-hidden="true"
                ></i>
                {{ $gettext("Assign Group Permissions to Rule") }}
            </h2>
            <span
                v-if="draft"
                class="toolbar-actions"
            >
                <label
                    class="active-toggle"
                    for="abac-rule-active"
                >
                    <ToggleSwitch
                        v-model="draft.active"
                        input-id="abac-rule-active"
                    />
                    {{
                        draft.active ? $gettext("Active") : $gettext("Inactive")
                    }}
                </label>
                <Button
                    severity="secondary"
                    variant="outlined"
                    :label="$gettext('Cancel')"
                    :disabled="isSaving"
                    @click="emit('cancel')"
                />
                <Button
                    :label="$gettext('Save')"
                    :disabled="!canSave || !isDirty"
                    :loading="isSaving"
                    @click="emit('save')"
                />
            </span>
        </header>
        <p
            v-if="!draft"
            class="empty"
        >
            {{
                $gettext("Select or create a rule to assign group permissions.")
            }}
        </p>
        <template v-else>
            <div class="table-wrapper">
                <table class="grants">
                    <caption class="sr-only">
                        {{
                            $gettext(
                                "Permissions granted to each group on resources matching this rule",
                            )
                        }}
                    </caption>
                    <thead>
                        <tr>
                            <th
                                scope="col"
                                class="name-cell"
                            >
                                {{ $gettext("Group") }}
                            </th>
                            <th
                                v-for="permission in PERMISSION_NAMES"
                                :key="permission"
                                scope="col"
                                class="check-cell"
                            >
                                <button
                                    type="button"
                                    class="grant-button"
                                    :aria-label="
                                        allGranted(permission)
                                            ? $gettext(
                                                  'Revoke %{permission} from all groups',
                                                  {
                                                      permission:
                                                          permissionLabel(
                                                              permission,
                                                          ),
                                                  },
                                              )
                                            : $gettext(
                                                  'Grant %{permission} to all groups',
                                                  {
                                                      permission:
                                                          permissionLabel(
                                                              permission,
                                                          ),
                                                  },
                                              )
                                    "
                                    :disabled="groups.length === 0"
                                    @click="toggleAll(permission)"
                                >
                                    <span>{{
                                        allGranted(permission)
                                            ? $gettext("Revoke")
                                            : $gettext("Grant")
                                    }}</span>
                                    <span>{{
                                        permissionLabel(permission)
                                    }}</span>
                                </button>
                            </th>
                            <th
                                scope="col"
                                class="action-cell"
                            >
                                <Button
                                    size="small"
                                    icon="pi pi-plus"
                                    class="add-group"
                                    :label="$gettext('Add Group')"
                                    @click="emit('add-group')"
                                />
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="group in groups"
                            :key="group.id"
                        >
                            <th
                                scope="row"
                                class="name-cell"
                            >
                                <span class="group-name">
                                    <span class="group-label">{{
                                        group.name
                                    }}</span>
                                    <button
                                        type="button"
                                        class="link-button"
                                        :aria-label="
                                            hasAny(group.id)
                                                ? $gettext(
                                                      'Clear permissions for %{group}',
                                                      { group: group.name },
                                                  )
                                                : $gettext(
                                                      'Select all permissions for %{group}',
                                                      { group: group.name },
                                                  )
                                        "
                                        @click="toggleGroup(group.id)"
                                    >
                                        {{
                                            hasAny(group.id)
                                                ? $gettext("Clear selection")
                                                : $gettext("Select all")
                                        }}
                                    </button>
                                </span>
                            </th>
                            <td
                                v-for="permission in PERMISSION_NAMES"
                                :key="permission"
                                class="check-cell"
                            >
                                <Checkbox
                                    binary
                                    :model-value="
                                        hasPermission(
                                            draft,
                                            group.id,
                                            permission,
                                        )
                                    "
                                    :aria-label="
                                        $gettext('%{permission} for %{group}', {
                                            permission:
                                                permissionLabel(permission),
                                            group: group.name,
                                        })
                                    "
                                    @update:model-value="
                                        setPermission(
                                            draft,
                                            group.id,
                                            permission,
                                            $event,
                                        )
                                    "
                                />
                            </td>
                            <td class="action-cell">
                                <button
                                    type="button"
                                    class="row-delete"
                                    :title="$gettext('Delete group')"
                                    :aria-label="
                                        $gettext('Delete group %{group}', {
                                            group: group.name,
                                        })
                                    "
                                    @click="emit('delete-group', group)"
                                >
                                    <i
                                        class="pi pi-trash"
                                        aria-hidden="true"
                                    ></i>
                                </button>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <p
                    v-if="groups.length === 0"
                    class="empty"
                >
                    {{ $gettext("There are no groups yet.") }}
                </p>
            </div>
        </template>
    </section>
</template>

<style scoped>
.active-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-right: 0.4rem;
    font-size: 1.25rem;
    font-weight: 500;
    color: var(--abac-text-primary);
}

.toolbar-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

.table-wrapper {
    flex: 1;
    overflow: auto;
    padding: 0 0.5rem;
}

.grants {
    width: 100%;
    border-collapse: collapse;
    font-size: 1.25rem;
}

.grants th,
.grants td {
    padding: 0.7rem 0;
    border-bottom: 1px solid var(--abac-border);
    text-align: center;
    vertical-align: middle;
}

.grants thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--abac-surface-bg);
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--abac-text-secondary);
}

.grants tbody tr {
    background: var(--abac-surface-card);
    color: var(--abac-text-primary);
}

.grants tbody tr:hover {
    background: var(--abac-row-hover);
}

.grants .name-cell {
    padding-left: 1.2rem;
    text-align: left;
}

.grants tbody .name-cell {
    font-weight: 400;
}

.check-cell {
    width: 7.6rem;
}

.action-cell {
    width: 9rem;
    padding-right: 1.2rem;
}

.grants tbody .action-cell {
    text-align: right;
}

.group-name {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-width: 0;
}

.group-label {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.grant-button {
    margin: 0 auto;
    padding: 0;
    border: none;
    background: none;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.1rem;
    color: var(--abac-accent);
    font: inherit;
    font-size: 1.2rem;
    font-weight: 600;
    text-decoration: underline;
    cursor: pointer;
}

.grant-button:hover {
    color: var(--abac-brand-light);
}

.grant-button:disabled {
    color: var(--abac-text-secondary);
    cursor: default;
    text-decoration: none;
}

.grant-button:focus-visible {
    outline: 2px solid var(--abac-accent);
    outline-offset: 2px;
}

.grants :deep(.add-group.p-button) {
    padding: 0.4rem 0.8rem;
    font-size: 1.2rem;
    font-weight: 500;
    line-height: 1.6;
    gap: 0.4rem;
    border-radius: 0.4rem;
    white-space: nowrap;
}

.grants :deep(.add-group .p-button-icon) {
    font-size: 0.8rem;
}

.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
}
</style>
