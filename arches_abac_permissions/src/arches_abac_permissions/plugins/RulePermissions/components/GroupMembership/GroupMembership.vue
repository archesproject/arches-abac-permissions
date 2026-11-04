<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Checkbox from "openvue/checkbox";
import InputText from "openvue/inputtext";
import ProgressSpinner from "openvue/progressspinner";
import Select from "openvue/select";
import { useToast } from "openvue/usetoast";

import {
    changeMembership,
    fetchAccounts,
} from "@/arches_abac_permissions/api.ts";
import AddAccountsDialog from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupMembership/components/AddAccountsDialog/AddAccountsDialog.vue";
import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import {
    accountDisplayName,
    accountMatchesFilter,
    groupHoldings,
} from "@/arches_abac_permissions/utils.ts";

import type { Account, Group } from "@/arches_abac_permissions/types";

const UNGROUPED = "none";
const MAX_VISIBLE_GROUPS = 2;

const { $gettext } = useGettext();
const noGroupsLabel = $gettext("<no groups>");
const toast = useToast();

const props = defineProps<{ groups: Group[] }>();
const emit = defineEmits<{
    (e: "add-group"): void;
    (e: "delete-group", group: Group): void;
}>();

const accounts = ref<Account[]>([]);
const isLoading = ref(true);
const isSaving = ref(false);
const groupFilter = ref<number | typeof UNGROUPED | null>(null);
const filter = ref("");
const checkedIds = ref<number[]>([]);
const activeId = ref<number | null>(null);
const isBulkEditing = ref(false);
const pendingGroup = ref<number | null>(null);
const showAddAccounts = ref(false);
// Hidden until the comp's "Add Account" behaviour is defined.
const ADD_ACCOUNT_ENABLED = false;

const groupsById = computed(
    () => new Map(props.groups.map((group) => [group.id, group])),
);

function groupNames(account: Account): string[] {
    return account.groups
        .map((id) => groupsById.value.get(id)?.name)
        .filter((name): name is string => Boolean(name));
}

const memberCounts = computed(
    () =>
        new Map(groupHoldings(accounts.value).map((h) => [h.groupId, h.count])),
);
const ungroupedCount = computed(
    () =>
        accounts.value.filter((account) => account.groups.length === 0).length,
);

const visibleAccounts = computed(() =>
    accounts.value.filter((account) => {
        if (groupFilter.value === UNGROUPED && account.groups.length) {
            return false;
        }
        if (
            typeof groupFilter.value === "number" &&
            !account.groups.includes(groupFilter.value)
        ) {
            return false;
        }
        return accountMatchesFilter(account, filter.value, groupNames(account));
    }),
);

const activeAccount = computed(
    () => accounts.value.find((a) => a.id === activeId.value) ?? null,
);
const checkedAccounts = computed(() =>
    accounts.value.filter((a) => checkedIds.value.includes(a.id)),
);
const editedAccounts = computed(() =>
    isBulkEditing.value
        ? checkedAccounts.value
        : activeAccount.value
          ? [activeAccount.value]
          : [],
);

const holdings = computed(() =>
    groupHoldings(editedAccounts.value)
        .map((h) => ({ ...h, group: groupsById.value.get(h.groupId) }))
        .filter((h) => h.group !== undefined)
        .sort((a, b) => a.group!.name.localeCompare(b.group!.name)),
);
const addableGroups = computed(() => {
    const total = editedAccounts.value.length;
    const full = new Set(
        holdings.value.filter((h) => h.count === total).map((h) => h.groupId),
    );
    return props.groups.filter((group) => !full.has(group.id));
});

function toggleFilter(value: number | typeof UNGROUPED): void {
    groupFilter.value = groupFilter.value === value ? null : value;
}

function toggleChecked(account: Account): void {
    checkedIds.value = checkedIds.value.includes(account.id)
        ? checkedIds.value.filter((id) => id !== account.id)
        : [...checkedIds.value, account.id];
    if (checkedIds.value.length === 0) {
        isBulkEditing.value = false;
    }
}

function selectAllVisible(): void {
    checkedIds.value = visibleAccounts.value.map((a) => a.id);
}

function clearChecked(): void {
    checkedIds.value = [];
    isBulkEditing.value = false;
}

function openAccount(account: Account): void {
    activeId.value = account.id;
    isBulkEditing.value = false;
}

function openBulkEdit(): void {
    isBulkEditing.value = true;
    activeId.value = null;
}

async function apply(add: number[], remove: number[]): Promise<void> {
    const ids = editedAccounts.value.map((a) => a.id);
    isSaving.value = true;
    try {
        mergeAccounts(await changeMembership(ids, add, remove));
    } catch (error) {
        showError($gettext("Unable to update group membership"), error);
    } finally {
        isSaving.value = false;
        pendingGroup.value = null;
    }
}

function mergeAccounts(updated: Account[]): void {
    const byId = new Map(updated.map((a) => [a.id, a]));
    accounts.value = accounts.value.map((a) => byId.get(a.id) ?? a);
}

function showError(summary: string, error: unknown): void {
    toast.add({
        severity: ERROR,
        life: DEFAULT_ERROR_TOAST_LIFE,
        summary,
        detail: error instanceof Error ? error.message : undefined,
    });
}

function initials(account: Account): string {
    const letters = `${account.first_name.charAt(0)}${account.last_name.charAt(0)}`;
    return (letters || account.username.charAt(0)).toUpperCase();
}

function formatDate(value: string | null): string {
    return value ? new Date(value).toLocaleString() : $gettext("Never");
}

watchEffect(loadAccounts);

async function loadAccounts(): Promise<void> {
    try {
        accounts.value = await fetchAccounts();
    } catch (error) {
        showError($gettext("Unable to load accounts"), error);
    } finally {
        isLoading.value = false;
    }
}
</script>

<template>
    <div
        class="membership-columns"
        :class="{ 'with-editor': editedAccounts.length > 0 }"
    >
        <section
            class="column"
            :aria-label="$gettext('Groups')"
        >
            <header class="column-header">
                <h2 class="column-title">
                    <i
                        class="pi pi-users"
                        aria-hidden="true"
                    ></i>
                    {{ $gettext("Groups") }}
                    <span class="count">{{ groups.length }}</span>
                </h2>
                <span class="toolbar-actions">
                    <button
                        v-if="groupFilter !== null"
                        type="button"
                        class="link-button"
                        :aria-label="$gettext('Clear group filter')"
                        @click="groupFilter = null"
                    >
                        {{ $gettext("Clear") }}
                    </button>
                    <Button
                        icon="pi pi-plus"
                        :label="$gettext('Add Group')"
                        @click="emit('add-group')"
                    />
                </span>
            </header>
            <ul class="item-list">
                <li
                    v-for="group in groups"
                    :key="group.id"
                    class="item-row"
                    :class="{ selected: groupFilter === group.id }"
                >
                    <button
                        type="button"
                        class="item-select"
                        :aria-pressed="groupFilter === group.id"
                        @click="toggleFilter(group.id)"
                    >
                        <i
                            class="pi pi-users row-icon"
                            aria-hidden="true"
                        ></i>
                        <span class="item-name">{{ group.name }}</span>
                        <span class="group-count">{{
                            memberCounts.get(group.id) ?? 0
                        }}</span>
                    </button>
                    <button
                        type="button"
                        class="row-delete"
                        :title="$gettext('Delete group')"
                        :aria-label="
                            $gettext('Delete group %{name}', {
                                name: group.name,
                            })
                        "
                        @click="emit('delete-group', group)"
                    >
                        <i
                            class="pi pi-trash"
                            aria-hidden="true"
                        ></i>
                    </button>
                </li>
                <li
                    class="item-row ungrouped"
                    :class="{ selected: groupFilter === UNGROUPED }"
                >
                    <button
                        type="button"
                        class="item-select"
                        :aria-pressed="groupFilter === UNGROUPED"
                        @click="toggleFilter(UNGROUPED)"
                    >
                        <i
                            class="pi pi-ban row-icon"
                            aria-hidden="true"
                        ></i>
                        <span class="item-name">{{
                            $gettext("No group affiliation")
                        }}</span>
                        <span class="group-count">{{ ungroupedCount }}</span>
                    </button>
                </li>
            </ul>
        </section>

        <section
            class="column"
            :aria-label="$gettext('Accounts')"
        >
            <header class="column-header">
                <h2 class="column-title">
                    <i
                        class="pi pi-user"
                        aria-hidden="true"
                    ></i>
                    {{ $gettext("Accounts") }}
                    <span class="count">{{
                        groupFilter !== null || filter
                            ? `${visibleAccounts.length} / ${accounts.length}`
                            : accounts.length
                    }}</span>
                </h2>
                <InputText
                    v-model="filter"
                    type="search"
                    class="header-filter"
                    :placeholder="$gettext('Filter…')"
                    :aria-label="$gettext('Filter accounts')"
                />
                <Button
                    v-if="ADD_ACCOUNT_ENABLED"
                    icon="pi pi-plus"
                    :label="$gettext('Add Account')"
                    @click="showAddAccounts = true"
                />
            </header>
            <div
                v-if="isLoading"
                class="loading"
                role="status"
            >
                <ProgressSpinner :aria-label="$gettext('Loading')" />
            </div>
            <div
                v-else
                class="account-body"
            >
                <div
                    v-if="checkedIds.length && visibleAccounts.length"
                    class="selection-bar"
                    role="group"
                    :aria-label="$gettext('Bulk actions')"
                >
                    <i
                        class="pi pi-check-square"
                        aria-hidden="true"
                    ></i>
                    <span class="selection-count">
                        {{
                            checkedIds.length === 1
                                ? $gettext("1 account selected")
                                : $gettext("%{count} accounts selected", {
                                      count: String(checkedIds.length),
                                  })
                        }}
                    </span>
                    <button
                        type="button"
                        class="link-button"
                        @click="selectAllVisible"
                    >
                        {{ $gettext("Select all") }}
                    </button>
                    <button
                        type="button"
                        class="link-button"
                        @click="clearChecked"
                    >
                        {{ $gettext("Clear") }}
                    </button>
                    <Button
                        size="small"
                        icon="pi pi-pencil"
                        class="edit-group"
                        :label="$gettext('Edit Group')"
                        @click="openBulkEdit"
                    />
                </div>
                <ul class="item-list">
                    <li
                        v-if="visibleAccounts.length === 0"
                        class="empty"
                    >
                        {{ $gettext("No accounts match") }}
                    </li>
                    <li
                        v-for="account in visibleAccounts"
                        :key="account.id"
                        class="item-row account-row"
                        :class="{
                            selected: account.id === activeId,
                            checked: checkedIds.includes(account.id),
                        }"
                    >
                        <Checkbox
                            class="account-check"
                            :binary="true"
                            :model-value="checkedIds.includes(account.id)"
                            :aria-label="
                                $gettext('Select %{name}', {
                                    name: accountDisplayName(account),
                                })
                            "
                            @update:model-value="toggleChecked(account)"
                        />
                        <button
                            type="button"
                            class="item-select stacked"
                            :aria-current="
                                account.id === activeId ? 'true' : undefined
                            "
                            @click="openAccount(account)"
                        >
                            <span class="line">
                                <span class="item-name account-name">{{
                                    accountDisplayName(account)
                                }}</span>
                                <span
                                    class="status-badge"
                                    :class="{
                                        'status-active': account.is_active,
                                    }"
                                >
                                    {{
                                        account.is_active
                                            ? $gettext("Active")
                                            : $gettext("Inactive")
                                    }}
                                </span>
                            </span>
                            <span class="line account-username"
                                >@{{ account.username }}</span
                            >
                            <span class="line">
                                <span
                                    class="account-groups"
                                    :class="{
                                        none: account.groups.length === 0,
                                    }"
                                >
                                    {{
                                        account.groups.length === 0
                                            ? noGroupsLabel
                                            : groupNames(account)
                                                  .slice(0, MAX_VISIBLE_GROUPS)
                                                  .join(", ")
                                    }}
                                </span>
                                <span
                                    v-if="
                                        account.groups.length >
                                        MAX_VISIBLE_GROUPS
                                    "
                                    class="more-pill"
                                >
                                    {{
                                        $gettext("+%{count} more", {
                                            count: String(
                                                account.groups.length -
                                                    MAX_VISIBLE_GROUPS,
                                            ),
                                        })
                                    }}
                                </span>
                            </span>
                        </button>
                    </li>
                </ul>
            </div>
        </section>

        <section
            v-if="editedAccounts.length > 0"
            class="column editor-column"
            :aria-label="$gettext('Group Membership')"
        >
            <header class="column-header">
                <h2 class="column-title editor-title">
                    <i
                        class="pi pi-user"
                        aria-hidden="true"
                    ></i>
                    <span class="truncate">
                        <template v-if="isBulkEditing">
                            {{
                                $gettext("%{count} Accounts Selected", {
                                    count: String(checkedAccounts.length),
                                })
                            }}
                        </template>
                        <template v-else-if="activeAccount">
                            {{ accountDisplayName(activeAccount) }}
                        </template>
                    </span>
                </h2>
            </header>
            <div class="editor">
                <template v-if="activeAccount && !isBulkEditing">
                    <div class="hero">
                        <div class="hero-head">
                            <span
                                class="avatar"
                                aria-hidden="true"
                                >{{ initials(activeAccount) }}</span
                            >
                            <div class="hero-text">
                                <span class="line">
                                    <span class="hero-name">{{
                                        accountDisplayName(activeAccount)
                                    }}</span>
                                    <span
                                        class="status-badge"
                                        :class="{
                                            'status-active':
                                                activeAccount.is_active,
                                        }"
                                    >
                                        {{
                                            activeAccount.is_active
                                                ? $gettext("Active")
                                                : $gettext("Inactive")
                                        }}
                                    </span>
                                </span>
                                <span
                                    v-if="activeAccount.is_superuser"
                                    class="hero-sub"
                                    >{{ $gettext("Superuser") }}</span
                                >
                            </div>
                        </div>
                        <dl class="dates">
                            <div>
                                <dt>{{ $gettext("Created") }}</dt>
                                <dd>
                                    {{ formatDate(activeAccount.date_joined) }}
                                </dd>
                            </div>
                            <span
                                class="dot"
                                aria-hidden="true"
                                >·</span
                            >
                            <div>
                                <dt>{{ $gettext("Last Login") }}</dt>
                                <dd>
                                    {{
                                        activeAccount.last_login
                                            ? formatDate(
                                                  activeAccount.last_login,
                                              )
                                            : $gettext("Never")
                                    }}
                                </dd>
                            </div>
                        </dl>
                    </div>
                </template>
                <div class="editor-body">
                    <dl
                        v-if="activeAccount && !isBulkEditing"
                        class="profile"
                    >
                        <div>
                            <dt class="section-label">
                                {{ $gettext("Username") }}
                            </dt>
                            <dd class="mono">{{ activeAccount.username }}</dd>
                        </div>
                        <div>
                            <dt class="section-label">
                                {{ $gettext("Email") }}
                            </dt>
                            <dd>{{ activeAccount.email || "—" }}</dd>
                        </div>
                    </dl>
                    <div
                        v-else
                        class="bulk-intro"
                    >
                        <i
                            class="pi pi-users"
                            aria-hidden="true"
                        ></i>
                        <span>
                            {{ $gettext("Editing group membership for") }}
                            <strong>{{
                                $gettext("%{count} accounts", {
                                    count: String(editedAccounts.length),
                                })
                            }}</strong>
                        </span>
                    </div>

                    <div
                        class="membership"
                        :class="{ divided: !isBulkEditing }"
                    >
                        <h3 class="section-label">
                            {{ $gettext("Group Membership") }}
                        </h3>
                        <p
                            v-if="isBulkEditing"
                            class="hint"
                        >
                            {{
                                $gettext(
                                    "Groups at reduced opacity are not held by all selected accounts.",
                                )
                            }}
                        </p>
                        <ul class="tags">
                            <li
                                v-if="holdings.length === 0"
                                class="no-groups"
                            >
                                {{
                                    isBulkEditing
                                        ? $gettext(
                                              "No groups assigned to any selected account",
                                          )
                                        : $gettext("No groups assigned")
                                }}
                            </li>
                            <li
                                v-for="holding in holdings"
                                :key="holding.groupId"
                                class="group-tag"
                                :class="{
                                    partial:
                                        holding.count < editedAccounts.length,
                                }"
                            >
                                {{ holding.group?.name }}
                                <span
                                    v-if="isBulkEditing"
                                    class="tag-count"
                                >
                                    ({{ holding.count }}/{{
                                        editedAccounts.length
                                    }})
                                </span>
                                <button
                                    type="button"
                                    class="tag-remove"
                                    :disabled="isSaving"
                                    :aria-label="
                                        $gettext('Remove from %{group}', {
                                            group: holding.group?.name ?? '',
                                        })
                                    "
                                    @click="apply([], [holding.groupId])"
                                >
                                    <i
                                        class="pi pi-times"
                                        aria-hidden="true"
                                    ></i>
                                </button>
                            </li>
                        </ul>
                        <Select
                            v-if="addableGroups.length > 0"
                            v-model="pendingGroup"
                            class="add-to-group"
                            :options="addableGroups"
                            option-label="name"
                            option-value="id"
                            :disabled="isSaving"
                            :aria-label="$gettext('Add to group')"
                            :placeholder="
                                isBulkEditing
                                    ? $gettext('Add to all selected…')
                                    : $gettext('Add to group…')
                            "
                            @update:model-value="
                                (id: number) => apply([id], [])
                            "
                        />
                    </div>
                </div>
            </div>
        </section>
        <AddAccountsDialog
            v-if="ADD_ACCOUNT_ENABLED"
            v-model:visible="showAddAccounts"
            :groups="groups"
            :accounts="accounts"
            :initial-group-id="
                typeof groupFilter === 'number' ? groupFilter : null
            "
            @updated="mergeAccounts"
        />
    </div>
</template>

<style scoped>
.membership-columns {
    display: grid;
    grid-template-columns: 46rem 46rem;
    grid-template-rows: auto minmax(0, 1fr);
    flex: 1;
    min-block-size: 0;
    overflow: auto;
    background: var(--p-abac-surface-bg);
}

.membership-columns.with-editor {
    grid-template-columns: 46rem 46rem minmax(32rem, 1fr);
}

@media (max-width: 87.5rem) {
    .membership-columns,
    .membership-columns.with-editor {
        grid-template-columns: 1fr;
        grid-template-rows: none;
        grid-auto-rows: minmax(30rem, auto);
    }

    .membership-columns .column {
        display: flex;
        flex-direction: column;
        grid-row: auto;
    }
}

.toolbar-actions {
    margin-inline-start: auto;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

.header-filter {
    flex: 1;
    min-inline-size: 6rem;
}

.item-list {
    list-style: none;
    margin: 0;
    padding: 0 0.5rem;
    overflow-y: auto;
    flex: 1;
}

.account-body {
    flex: 1;
    min-block-size: 0;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
}

.account-body .item-list {
    overflow: visible;
}

.item-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding-inline-end: 0.8rem;
    border-block-end: 0.1rem solid var(--p-abac-border);
    background: var(--p-abac-surface-card);
    color: var(--p-abac-text-primary);
    font-size: 1.25rem;
}

.item-row:hover {
    background: var(--p-abac-row-hover);
}

.item-row.checked {
    background: var(--p-abac-accent-subtle);
}

.item-row.selected {
    background: var(--p-abac-accent-subtle);
    color: var(--p-abac-brand-light);
}

.item-row.selected .item-name {
    font-weight: 600;
}

.item-row.ungrouped {
    border-block-start: 0.1rem solid var(--p-abac-border);
    opacity: 0.8;
}

.item-row.ungrouped .item-name {
    font-style: italic;
    color: var(--p-abac-text-secondary);
}

.row-icon {
    flex-shrink: 0;
    font-size: 1.3rem;
    color: var(--p-abac-text-secondary);
}

.item-row.selected .row-icon {
    color: var(--p-abac-brand-light);
}

.group-count {
    flex-shrink: 0;
    margin-inline-end: 0.6rem;
    padding: 0.1rem 0.6rem;
    border: 0.1rem solid var(--p-abac-border);
    border-radius: 0.8rem;
    background: var(--p-abac-surface-bg);
    color: var(--p-abac-text-secondary);
    font-size: 1.05rem;
    font-weight: 500;
}

.item-select {
    flex: 1;
    min-inline-size: 0;
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding-block: 0.8rem;
    padding-inline: 1.2rem 0;
    border: none;
    background: none;
    text-align: start;
    cursor: pointer;
    color: inherit;
    font: inherit;
}

.item-select:focus-visible {
    outline: 0.2rem solid var(--p-abac-accent);
    outline-offset: -0.2rem;
}

.item-name {
    flex: 1;
    min-inline-size: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.account-row {
    align-items: flex-start;
}

/* Centre the checkbox on the fixed-height first (name) line. */
.account-check {
    margin-block: 1.4rem 0;
    margin-inline: 1.2rem 0;
}

.item-select.stacked > .line:first-child {
    min-block-size: 2.4rem;
}

.item-select.stacked {
    flex-direction: column;
    align-items: stretch;
    gap: 0.3rem;
    padding-block: 0.9rem;
    padding-inline: 0.6rem 0;
}

.line {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-inline-size: 0;
}

.account-name {
    flex: 0 1 auto;
    font-size: 1.35rem;
}

.account-username {
    font-size: 1.15rem;
    font-weight: 600;
    color: color-mix(
        in srgb,
        var(--p-abac-accent) 80%,
        var(--p-abac-text-secondary)
    );
}

.account-groups {
    font-size: 1.2rem;
    color: var(--p-abac-text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.account-groups.none {
    font-style: italic;
}

.selection-bar {
    position: sticky;
    inset-block-start: 0;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.6rem 1rem;
    border-block-end: 0.1rem solid var(--p-abac-border);
    background: var(--p-abac-surface-bg);
}

.selection-bar > .pi {
    font-size: 1.1rem;
    color: var(--p-abac-accent);
}

.selection-count {
    flex: 1;
    font-size: 1.15rem;
    font-weight: 600;
    color: color-mix(
        in srgb,
        var(--p-abac-accent) 75%,
        var(--p-abac-text-primary)
    );
}

.selection-bar :deep(.edit-group.p-button) {
    padding: 0.3rem 0.8rem;
    font-size: 1.05rem;
    font-weight: 500;
    line-height: 1.6;
    gap: 0.3rem;
    border-radius: 0.4rem;
}

.selection-bar :deep(.edit-group .p-button-icon) {
    font-size: 0.8rem;
}

.selection-bar :deep(.edit-group .p-button-icon) {
    font-size: 0.8rem;
}

.loading {
    display: flex;
    justify-content: center;
    padding: 2rem;
}

.editor-title {
    flex: 1;
    min-inline-size: 0;
}

.truncate {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.editor {
    flex: 1;
    overflow-y: auto;
}

.editor-body {
    padding-block: 1.6rem;
    padding-inline: 2rem 1.4rem;
}

.hero + .editor-body {
    padding-block-start: 2rem;
}

.hero {
    padding-block: 1.6rem;
    padding-inline: 2rem 1.4rem;
    border-block-end: 0.1rem solid var(--p-abac-border);
    background: var(--p-abac-surface-card);
}

.hero-head {
    display: flex;
    align-items: center;
    gap: 1.4rem;
    margin-block-end: 1.6rem;
}

.avatar {
    flex-shrink: 0;
    inline-size: 4.8rem;
    block-size: 4.8rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 0.2rem solid
        color-mix(in srgb, var(--p-abac-accent) 40%, transparent);
    border-radius: 50%;
    background: var(--p-abac-accent-subtle);
    color: var(--p-abac-accent);
    font-size: 1.8rem;
    font-weight: 700;
}

.hero-text {
    min-inline-size: 0;
}

.hero-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--p-abac-text-primary);
}

.hero-sub {
    display: block;
    margin-block-start: 0.2rem;
    font-size: 1.25rem;
    color: var(--p-abac-text-secondary);
}

.dates {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1rem;
    margin: 0;
}

.dates > div {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
}

.dates dt {
    font-size: 1.05rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--p-abac-text-secondary);
}

.dates dd,
.profile dd {
    margin: 0;
    font-size: 1.25rem;
    color: var(--p-abac-text-primary);
}

.dot {
    color: var(--p-abac-border);
}

.profile {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
    margin-block: 0 2.4rem;
    margin-inline: 0;
}

.profile > div {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}

.profile dd {
    font-size: 1.35rem;
    overflow-wrap: anywhere;
}

.profile dd.mono {
    font-family: monospace;
    font-size: 1.3rem;
}

.bulk-intro {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    margin-block-end: 2rem;
    padding-block-end: 1.6rem;
    border-block-end: 0.1rem solid var(--p-abac-border);
    font-size: 1.3rem;
    color: var(--p-abac-text-secondary);
}

.bulk-intro .pi {
    font-size: 1.6rem;
    color: var(--p-abac-accent);
}

.bulk-intro strong {
    color: var(--p-abac-text-primary);
}

.membership.divided {
    padding-block-start: 1.6rem;
    border-block-start: 0.1rem solid var(--p-abac-border);
}

.membership .section-label {
    font-weight: 700;
    margin-block-end: 1rem;
}

.membership .section-label:has(+ .hint) {
    margin-block-end: 0.6rem;
}

.hint {
    margin-block: 0 1rem;
    margin-inline: 0;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}

.tags {
    list-style: none;
    margin-block: 0 1.2rem;
    margin-inline: 0;
    padding: 0;
    min-block-size: 2.6rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
}

.no-groups {
    align-self: center;
    font-size: 1.25rem;
    font-style: italic;
    color: var(--p-abac-text-secondary);
}

.group-tag.partial {
    background: var(--p-abac-row-hover);
    border-color: var(--p-abac-border);
}

.tag-count {
    font-size: 1rem;
    opacity: 0.75;
}

.tag-remove {
    display: flex;
    align-items: center;
    padding: 0.2rem;
    border: none;
    background: none;
    color: var(--p-abac-brand-light);
    opacity: 0.6;
    cursor: pointer;
    line-height: 1;
}

.tag-remove .pi {
    font-size: 0.9rem;
}

.tag-remove:hover,
.tag-remove:focus-visible,
.group-tag.partial .tag-remove {
    opacity: 1;
}

.tag-remove:focus-visible {
    outline: 0.2rem solid var(--p-abac-accent);
    border-radius: 50%;
}

.add-to-group {
    inline-size: 100%;
    max-inline-size: 30rem;
}
</style>
