<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useGettext } from "vue3-gettext";

import ConfirmDialog from "openvue/confirmdialog";
import ProgressSpinner from "openvue/progressspinner";
import Toast from "openvue/toast";
import { useConfirm } from "openvue/useconfirm";
import { useToast } from "openvue/usetoast";

import {
    createRule,
    deleteGroup,
    deleteRule,
    fetchGroups,
    fetchResourceModels,
    fetchResourceSets,
    fetchRuleTypes,
    fetchRules,
    updateRule,
} from "@/arches_abac_permissions/api.ts";
import AddGroupDialog from "@/arches_abac_permissions/components/AddGroupDialog.vue";
import GroupMembership from "@/arches_abac_permissions/components/GroupMembership.vue";
import GroupPermissions from "@/arches_abac_permissions/components/GroupPermissions.vue";
import RuleConfiguration from "@/arches_abac_permissions/components/RuleConfiguration.vue";
import RuleList from "@/arches_abac_permissions/components/RuleList.vue";
import {
    DEFAULT_ERROR_TOAST_LIFE,
    DEFAULT_SUCCESS_TOAST_LIFE,
    ERROR,
    SUCCESS,
} from "@/arches_abac_permissions/constants.ts";
import {
    draftFromRule,
    draftToPayload,
    isDraftComplete,
    newDraft,
    serializeDraft,
} from "@/arches_abac_permissions/utils.ts";

import type {
    Group,
    ResourceModel,
    ResourceSet,
    Rule,
    RuleDraft,
    RuleTypeInfo,
} from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();
const confirm = useConfirm();
const toast = useToast();

const rules = ref<Rule[]>([]);
const groups = ref<Group[]>([]);
const ruleTypes = ref<RuleTypeInfo[]>([]);
const resourceModels = ref<ResourceModel[]>([]);
const resourceSets = ref<ResourceSet[]>([]);
const isLoading = ref(true);
const isSaving = ref(false);
const showAddGroup = ref(false);
const mode = ref<"rule" | "membership">("rule");
const modeOptions = computed<
    { value: "rule" | "membership"; label: string; icon: string }[]
>(() => [
    { value: "rule", label: $gettext("By Rule"), icon: "pi pi-filter" },
    {
        value: "membership",
        label: $gettext("Group Membership"),
        icon: "pi pi-id-card",
    },
]);

const draft = ref<RuleDraft | null>(null);
const savedSnapshot = ref("");

const savedRule = computed(
    () => rules.value.find((rule) => rule.id === draft.value?.id) ?? null,
);
const isDirty = computed(
    () =>
        draft.value !== null &&
        serializeDraft(draft.value) !== savedSnapshot.value,
);
const canSave = computed(
    () => draft.value !== null && isDraftComplete(draft.value),
);

function showError(summary: string, error: unknown) {
    toast.add({
        severity: ERROR,
        life: DEFAULT_ERROR_TOAST_LIFE,
        summary,
        detail: error instanceof Error ? error.message : undefined,
    });
}

function sortGroups(list: Group[]) {
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
}

function sortRules(list: Rule[]) {
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
}

function setDraft(value: RuleDraft | null) {
    draft.value = value;
    savedSnapshot.value = value ? serializeDraft(value) : "";
}

function confirmDestructive(
    message: string,
    header: string,
    label: string,
    accept: () => void,
) {
    confirm.require({
        message,
        header,
        icon: "fa fa-exclamation-triangle",
        acceptProps: { label, severity: "danger" },
        rejectProps: { label: $gettext("Cancel"), severity: "secondary" },
        accept,
    });
}

function discardUnsavedThen(proceed: () => void) {
    if (!isDirty.value) {
        proceed();
        return;
    }
    confirmDestructive(
        $gettext("You have unsaved changes to this rule. Discard them?"),
        $gettext("Unsaved changes"),
        $gettext("Discard"),
        proceed,
    );
}

function selectRule(rule: Rule) {
    if (draft.value?.id === rule.id) {
        return;
    }
    discardUnsavedThen(() => setDraft(draftFromRule(rule)));
}

function startNewRule() {
    discardUnsavedThen(() => setDraft(null));
}

function pickRuleType(ruleType: RuleTypeInfo) {
    setDraft(newDraft(ruleType.key));
}

function cancel() {
    const saved = rules.value.find((rule) => rule.id === draft.value?.id);
    setDraft(saved ? draftFromRule(saved) : null);
}

async function save() {
    if (!draft.value || !canSave.value) {
        return;
    }
    isSaving.value = true;
    try {
        const payload = draftToPayload(draft.value);
        const saved = draft.value.id
            ? await updateRule(draft.value.id, payload)
            : await createRule(payload);
        rules.value = sortRules([
            ...rules.value.filter((rule) => rule.id !== saved.id),
            saved,
        ]);
        setDraft(draftFromRule(saved));
        toast.add({
            severity: SUCCESS,
            life: DEFAULT_SUCCESS_TOAST_LIFE,
            summary: $gettext("Rule saved"),
        });
    } catch (error) {
        showError($gettext("Unable to save rule"), error);
    } finally {
        isSaving.value = false;
    }
}

function requestDeleteRule(rule: Rule) {
    confirmDestructive(
        $gettext(
            "Delete the rule “%{name}”? This also removes its group permissions.",
            {
                name: rule.name,
            },
        ),
        $gettext("Confirm deletion"),
        $gettext("Delete"),
        async () => {
            try {
                await deleteRule(rule.id);
            } catch (error) {
                showError($gettext("Unable to delete rule"), error);
                return;
            }
            rules.value = rules.value.filter(
                (existing) => existing.id !== rule.id,
            );
            if (draft.value?.id === rule.id) {
                setDraft(null);
            }
        },
    );
}

function requestDeleteGroup(group: Group) {
    confirmDestructive(
        $gettext(
            "Delete the group “%{name}”? Its permissions on every rule will also be removed.",
            { name: group.name },
        ),
        $gettext("Confirm deletion"),
        $gettext("Delete"),
        async () => {
            try {
                await deleteGroup(group.id);
            } catch (error) {
                showError($gettext("Unable to delete group"), error);
                return;
            }
            groups.value = groups.value.filter(
                (existing) => existing.id !== group.id,
            );
            rules.value = rules.value.map((rule) => ({
                ...rule,
                group_permissions: rule.group_permissions.filter(
                    (grant) => grant.groupid !== group.id,
                ),
            }));
            if (draft.value) {
                const wasDirty = isDirty.value;
                delete draft.value.grants[group.id];
                if (!wasDirty) {
                    savedSnapshot.value = serializeDraft(draft.value);
                }
            }
        },
    );
}

function onGroupCreated(group: Group) {
    groups.value = sortGroups([...groups.value, group]);
}

function warnBeforeUnload(event: BeforeUnloadEvent) {
    if (isDirty.value) {
        event.preventDefault();
    }
}

onMounted(async () => {
    window.addEventListener("beforeunload", warnBeforeUnload);
    try {
        const [
            loadedRules,
            loadedGroups,
            loadedTypes,
            loadedModels,
            loadedSets,
        ] = await Promise.all([
            fetchRules(),
            fetchGroups(),
            fetchRuleTypes(),
            fetchResourceModels(),
            fetchResourceSets(),
        ]);
        rules.value = sortRules(loadedRules);
        groups.value = sortGroups(loadedGroups);
        ruleTypes.value = loadedTypes;
        resourceModels.value = loadedModels;
        resourceSets.value = loadedSets;
    } catch (error) {
        showError($gettext("Unable to load rule permissions"), error);
    } finally {
        isLoading.value = false;
    }
});

onBeforeUnmount(() => {
    window.removeEventListener("beforeunload", warnBeforeUnload);
});
</script>

<template>
    <div class="rule-permissions">
        <h1 class="sr-only">{{ $gettext("Rule Permissions") }}</h1>
        <div
            v-if="isLoading"
            class="loading"
            role="status"
        >
            <ProgressSpinner :aria-label="$gettext('Loading')" />
        </div>
        <template v-else>
            <div class="mode-bar">
                <span
                    id="abac-mode-label"
                    class="mode-title"
                    >{{ $gettext("Set permissions by") }}</span
                >
                <div
                    class="mode-toggle"
                    role="group"
                    aria-labelledby="abac-mode-label"
                >
                    <button
                        v-for="option in modeOptions"
                        :key="option.value"
                        type="button"
                        class="mode-option"
                        :class="{ active: mode === option.value }"
                        :aria-pressed="mode === option.value"
                        @click="mode = option.value"
                    >
                        <i
                            :class="option.icon"
                            aria-hidden="true"
                        ></i>
                        {{ option.label }}
                    </button>
                </div>
            </div>
            <GroupMembership
                v-show="mode === 'membership'"
                :groups="groups"
                @add-group="showAddGroup = true"
                @delete-group="requestDeleteGroup"
            />
            <div
                v-show="mode === 'rule'"
                class="columns"
                :class="{ 'two-columns': !draft }"
            >
                <RuleList
                    :rules="rules"
                    :groups="groups"
                    :rule-types="ruleTypes"
                    :selected-id="draft?.id ?? null"
                    @select="selectRule"
                    @add="startNewRule"
                    @delete="requestDeleteRule"
                />
                <RuleConfiguration
                    v-model="draft"
                    :rule-types="ruleTypes"
                    :resource-models="resourceModels"
                    :resource-sets="resourceSets"
                    :saved-rule="savedRule"
                    @pick="pickRuleType"
                />
                <GroupPermissions
                    v-if="draft"
                    v-model="draft"
                    :groups="groups"
                    :can-save="canSave"
                    :is-dirty="isDirty"
                    :is-saving="isSaving"
                    @save="save"
                    @cancel="cancel"
                    @add-group="showAddGroup = true"
                    @delete-group="requestDeleteGroup"
                />
            </div>
        </template>
        <AddGroupDialog
            v-model:visible="showAddGroup"
            @created="onGroupCreated"
        />
        <Toast />
        <ConfirmDialog :draggable="false" />
    </div>
</template>

<style>
.rule-permissions {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-size: 1.4rem;
    color: var(--p-text-color);
}

/* Arches sets the root font size to 62.5%, which shrinks rem-based controls. */
.rule-permissions {
    --p-button-padding-y: 0.7rem;
    --p-button-padding-x: 1.4rem;
    --p-button-icon-only-width: 3.6rem;
    --p-togglebutton-padding: 0.6rem 1.6rem;
    --p-checkbox-width: 1.4rem;
    --p-checkbox-height: 1.4rem;
    --p-checkbox-icon-size: 1rem;
    --p-toggleswitch-width: 3.6rem;
    --p-toggleswitch-height: 2rem;
    --p-toggleswitch-handle-size: 1.6rem;
    --p-toggleswitch-gap: 0.2rem;
    --abac-surface-bg: #f5f6fa;
    --abac-border: #dde2ef;
    --abac-text-secondary: #5a6a8a;
    --abac-accent: #4a90d9;
    --abac-surface-card: #ffffff;
    --abac-text-primary: #1a2236;
    --abac-accent-subtle: #b8d4f0;
    --abac-accent-tint: rgba(74, 144, 217, 0.1);
    --abac-row-hover: #e8f2fb;
    --abac-brand-light: #3d5499;
    --abac-danger: #e53e3e;
    --abac-status-active-bg: #f0fdf4;
    --abac-status-active-text: #166534;
    --abac-status-active-border: #bbf7d0;
}

.rule-permissions .p-button,
.rule-permissions .p-togglebutton,
.rule-permissions .p-inputtext,
.rule-permissions .p-textarea,
.rule-permissions .p-select,
.rule-permissions .p-select-label,
.rule-permissions .p-select-option {
    font-size: 1.4rem;
}

.rule-permissions .p-inputtext,
.rule-permissions .p-textarea,
.rule-permissions .p-select-label {
    padding: 0.9rem 1rem;
    font-size: 1.35rem;
}

.rule-permissions .columns {
    display: grid;
    grid-template-columns: 46rem minmax(30rem, 1fr) minmax(38rem, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    flex: 1;
    min-height: 0;
}

.rule-permissions .columns {
    overflow: auto;
}

.rule-permissions .columns.two-columns {
    grid-template-columns: 46rem minmax(30rem, 1fr);
}

@media (max-width: 1200px) {
    .rule-permissions .columns,
    .rule-permissions .columns.two-columns {
        grid-template-columns: 1fr;
        grid-template-rows: none;
        grid-auto-rows: minmax(30rem, auto);
    }

    .rule-permissions .columns .column {
        display: flex;
        flex-direction: column;
        grid-row: auto;
        border-right: none;
        border-bottom: 1px solid var(--p-content-border-color);
    }
}

.rule-permissions .mode-bar {
    display: flex;
    align-items: center;
    gap: 1.6rem;
    padding: 1.2rem 2rem;
    border-bottom: 1px solid var(--abac-border);
    background: var(--abac-surface-card);
}

.rule-permissions .mode-title {
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--abac-text-primary);
}

.rule-permissions .mode-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem;
    background: var(--abac-surface-card);
    border: 1px solid var(--abac-border);
    border-radius: 0.8rem;
}

.rule-permissions .mode-option {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1.2rem;
    border: none;
    border-radius: 0.6rem;
    background: transparent;
    color: var(--abac-text-secondary);
    font: inherit;
    font-size: 1.25rem;
    font-weight: 600;
    cursor: pointer;
}

.rule-permissions .mode-option i {
    font-size: 1.1rem;
}

.rule-permissions .mode-option:hover,
.rule-permissions .mode-option.active {
    background: var(--abac-accent-subtle);
}

.rule-permissions .mode-option.active {
    color: var(--abac-brand-light);
}

.rule-permissions .mode-option:focus-visible {
    outline: 2px solid var(--abac-accent);
    outline-offset: 1px;
}

.rule-permissions .toolbar-actions {
    margin-left: auto;
}

.rule-permissions .loading {
    display: flex;
    justify-content: center;
    padding: 4rem;
}

/* Subgrid rows keep every column header the same height. */
.rule-permissions .column {
    display: grid;
    grid-row: span 2;
    grid-template-rows: subgrid;
    min-height: 0;
    background: var(--abac-surface-bg);
    border-right: 1px solid var(--abac-border);
}

.rule-permissions .column > :not(.column-header) {
    min-height: 0;
}

.rule-permissions .column-header,
.rule-permissions .toolbar {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.9rem 1.2rem;
    border-bottom: 1px solid var(--abac-border);
}

.rule-permissions .column-header {
    background: var(--abac-surface-bg);
}

.rule-permissions .column-title {
    margin: 0;
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--abac-text-secondary);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
    white-space: nowrap;
}

.rule-permissions .column-header .p-button {
    padding: 0.2rem 0.9rem;
    font-size: 1.3rem;
    font-weight: 500;
    line-height: 1.6;
    gap: 0.4rem;
    border-radius: 0.4rem;
    flex-shrink: 0;
}

.rule-permissions .column-header .p-button .p-button-icon {
    font-size: 0.9rem;
}

.rule-permissions .column-header .header-filter {
    flex: 1;
    min-width: 6rem;
    padding: 0.6rem 0.7rem;
    font-size: 1.15rem;
    border-radius: 0.5rem;
}

.rule-permissions .count {
    font-size: 1.1rem;
    font-weight: 500;
    background: var(--abac-border);
    border-radius: 1rem;
    padding: 0.1rem 0.7rem;
}

.rule-permissions .empty {
    padding: 1.6rem;
    text-align: center;
    font-size: 1.25rem;
    font-style: italic;
    color: var(--abac-text-secondary);
}

.rule-permissions .field {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    max-width: 90rem;
}

.rule-permissions .field label,
.rule-permissions .section-label {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--abac-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.rule-permissions .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
    padding: 0.3rem 0.8rem;
    border: 1px solid var(--abac-border);
    border-radius: 2rem;
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--abac-text-secondary);
    background: var(--abac-surface-bg);
}

.rule-permissions .status-badge::before {
    content: "";
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: currentColor;
}

.rule-permissions .status-badge.status-active {
    color: var(--abac-status-active-text);
    background: var(--abac-status-active-bg);
    border-color: var(--abac-status-active-border);
}

.rule-permissions .more-pill {
    flex-shrink: 0;
    padding: 0.1rem 0.6rem;
    border: 1px solid var(--abac-border);
    border-radius: 0.8rem;
    font-size: 1.1rem;
    font-weight: 600;
    white-space: nowrap;
    color: var(--abac-text-secondary);
    background: var(--abac-surface-bg);
}

.rule-permissions .row-delete {
    flex-shrink: 0;
    padding: 0.3rem 0.5rem;
    border: none;
    border-radius: 0.4rem;
    background: none;
    color: var(--abac-text-secondary);
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
}

.rule-permissions .row-delete:hover {
    color: var(--abac-danger);
    background: rgba(229, 62, 62, 0.1);
}

.rule-permissions .link-button {
    padding: 0 0.2rem;
    border: none;
    background: none;
    color: var(--abac-accent);
    font: inherit;
    font-size: 1.15rem;
    font-weight: 600;
    text-decoration: underline;
    text-underline-offset: 2px;
    white-space: nowrap;
    cursor: pointer;
}

.rule-permissions .row-delete:focus-visible,
.rule-permissions .link-button:focus-visible {
    outline: 2px solid var(--abac-accent);
    outline-offset: 1px;
}

.rule-permissions .group-tag {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.6rem 0.3rem 1rem;
    border: 1px solid color-mix(in srgb, var(--abac-accent) 30%, transparent);
    border-radius: 2rem;
    background: var(--abac-accent-subtle);
    color: color-mix(in srgb, var(--abac-accent) 75%, var(--abac-text-primary));
    font-size: 1.15rem;
    font-weight: 600;
    white-space: nowrap;
}

.rule-permissions .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
}
</style>
