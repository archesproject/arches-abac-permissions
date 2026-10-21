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
    fetchRuleTypes,
    fetchRules,
    updateRule,
} from "@/arches_abac_permissions/api.ts";
import AddGroupDialog from "@/arches_abac_permissions/components/AddGroupDialog.vue";
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
const isLoading = ref(true);
const isSaving = ref(false);
const showAddGroup = ref(false);

const draft = ref<RuleDraft | null>(null);
const savedSnapshot = ref("");

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
            "Delete the rule “%{ name }”? This also removes its group permissions.",
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
            "Delete the group “%{ name }”? Its permissions on every rule will also be removed.",
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
        const [loadedRules, loadedGroups, loadedTypes, loadedModels] =
            await Promise.all([
                fetchRules(),
                fetchGroups(),
                fetchRuleTypes(),
                fetchResourceModels(),
            ]);
        rules.value = sortRules(loadedRules);
        groups.value = sortGroups(loadedGroups);
        ruleTypes.value = loadedTypes;
        resourceModels.value = loadedModels;
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
        <div
            v-else
            class="columns"
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
                @pick="pickRuleType"
            />
            <GroupPermissions
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
    height: 100%;
    font-size: 1.4rem;
    color: var(--p-text-color);
}

.rule-permissions .columns {
    display: grid;
    grid-template-columns: minmax(24rem, 30rem) minmax(30rem, 1fr) minmax(
            38rem,
            52rem
        );
    height: 100%;
}

.rule-permissions .loading {
    display: flex;
    justify-content: center;
    padding: 4rem;
}

.rule-permissions .column {
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--p-content-background);
    border-right: 1px solid var(--p-content-border-color);
}

.rule-permissions .column-header,
.rule-permissions .toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--p-content-border-color);
}

.rule-permissions .column-title {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.rule-permissions .empty {
    padding: 1.5rem 1rem;
    text-align: center;
    color: var(--p-text-muted-color);
}

.rule-permissions .field {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
}

.rule-permissions .field label {
    font-weight: 600;
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
