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

function toggleAll(permission: PermissionName, granted: boolean) {
    if (draft.value) {
        setPermissionForAllGroups(
            draft.value,
            props.groups,
            permission,
            granted,
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
            <div class="toolbar">
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
                <span class="toolbar-actions">
                    <Button
                        size="small"
                        severity="secondary"
                        :label="$gettext('Cancel')"
                        :disabled="isSaving"
                        @click="emit('cancel')"
                    />
                    <Button
                        size="small"
                        :label="$gettext('Save')"
                        :disabled="!canSave || !isDirty"
                        :loading="isSaving"
                        @click="emit('save')"
                    />
                </span>
            </div>
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
                            <th scope="col">{{ $gettext("Group") }}</th>
                            <th
                                v-for="permission in PERMISSION_NAMES"
                                :key="permission"
                                scope="col"
                            >
                                <div class="permission-heading">
                                    {{ permissionLabel(permission) }}
                                    <span class="bulk-actions">
                                        <button
                                            type="button"
                                            class="link-button"
                                            :aria-label="
                                                $gettext(
                                                    'Grant %{ permission } to all groups',
                                                    {
                                                        permission:
                                                            permissionLabel(
                                                                permission,
                                                            ),
                                                    },
                                                )
                                            "
                                            @click="toggleAll(permission, true)"
                                        >
                                            {{ $gettext("Grant all") }}
                                        </button>
                                        <button
                                            type="button"
                                            class="link-button"
                                            :aria-label="
                                                $gettext(
                                                    'Revoke %{ permission } from all groups',
                                                    {
                                                        permission:
                                                            permissionLabel(
                                                                permission,
                                                            ),
                                                    },
                                                )
                                            "
                                            @click="
                                                toggleAll(permission, false)
                                            "
                                        >
                                            {{ $gettext("Revoke all") }}
                                        </button>
                                    </span>
                                </div>
                            </th>
                            <th scope="col">
                                <span class="sr-only">{{
                                    $gettext("Actions")
                                }}</span>
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="group in groups"
                            :key="group.id"
                        >
                            <th scope="row">
                                <div class="group-name">
                                    <span>{{ group.name }}</span>
                                    <span class="bulk-actions">
                                        <button
                                            type="button"
                                            class="link-button"
                                            :aria-label="
                                                $gettext(
                                                    'Select all permissions for %{ group }',
                                                    { group: group.name },
                                                )
                                            "
                                            @click="
                                                setGroupPermissions(
                                                    draft,
                                                    group.id,
                                                    PERMISSION_NAMES,
                                                )
                                            "
                                        >
                                            {{ $gettext("Select all") }}
                                        </button>
                                        <button
                                            type="button"
                                            class="link-button"
                                            :aria-label="
                                                $gettext(
                                                    'Clear permissions for %{ group }',
                                                    { group: group.name },
                                                )
                                            "
                                            @click="
                                                setGroupPermissions(
                                                    draft,
                                                    group.id,
                                                    [],
                                                )
                                            "
                                        >
                                            {{ $gettext("Clear") }}
                                        </button>
                                    </span>
                                </div>
                            </th>
                            <td
                                v-for="permission in PERMISSION_NAMES"
                                :key="permission"
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
                                        $gettext(
                                            '%{ permission } for %{ group }',
                                            {
                                                permission:
                                                    permissionLabel(permission),
                                                group: group.name,
                                            },
                                        )
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
                            <td>
                                <Button
                                    icon="pi pi-trash"
                                    severity="danger"
                                    variant="text"
                                    size="small"
                                    :aria-label="
                                        $gettext('Delete group %{ group }', {
                                            group: group.name,
                                        })
                                    "
                                    @click="emit('delete-group', group)"
                                />
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
            <div class="toolbar footer">
                <Button
                    size="small"
                    variant="outlined"
                    icon="pi pi-plus"
                    :label="$gettext('Add Group')"
                    @click="emit('add-group')"
                />
            </div>
        </template>
    </section>
</template>

<style scoped>
.active-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
}

.toolbar-actions {
    margin-left: auto;
    display: flex;
    gap: 0.5rem;
}

.footer {
    border-top: 1px solid var(--p-content-border-color);
    border-bottom: none;
}

.table-wrapper {
    flex: 1;
    overflow: auto;
}

.grants {
    width: 100%;
    border-collapse: collapse;
}

.grants th,
.grants td {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--p-content-border-color);
    text-align: center;
    vertical-align: middle;
}

.grants th:first-child {
    text-align: left;
}

.group-name {
    font-weight: 600;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}

.permission-heading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2rem;
}

.bulk-actions {
    display: flex;
    gap: 0.5rem;
    font-weight: 400;
}

.link-button {
    border: none;
    background: none;
    padding: 0;
    color: var(--p-primary-color);
    font: inherit;
    font-size: 1.1rem;
    cursor: pointer;
    text-decoration: underline;
}

.link-button:focus-visible {
    outline: 2px solid var(--p-primary-color);
    outline-offset: 2px;
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
