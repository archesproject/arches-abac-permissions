<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Dialog from "openvue/dialog";
import Message from "openvue/message";
import MultiSelect from "openvue/multiselect";
import Select from "openvue/select";

import { changeMembership } from "@/arches_abac_permissions/api.ts";
import { accountDisplayName } from "@/arches_abac_permissions/utils.ts";

import type { Account, Group } from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

const visible = defineModel<boolean>("visible", { required: true });
const props = defineProps<{
    groups: Group[];
    accounts: Account[];
    initialGroupId: number | null;
}>();
const emit = defineEmits<{ (e: "updated", accounts: Account[]): void }>();

const groupId = ref<number | null>(null);
const accountIds = ref<number[]>([]);
const error = ref("");
const isSaving = ref(false);

// Only accounts not already in the chosen group.
const candidates = computed(() =>
    props.accounts
        .filter(
            (account) =>
                groupId.value === null ||
                !account.groups.includes(groupId.value),
        )
        .map((account) => ({
            id: account.id,
            label: `${accountDisplayName(account)} (@${account.username})`,
        })),
);

watch(visible, (isVisible) => {
    if (isVisible) {
        groupId.value = props.initialGroupId;
        accountIds.value = [];
        error.value = "";
    }
});

watch(groupId, () => {
    const allowed = new Set(candidates.value.map((c) => c.id));
    accountIds.value = accountIds.value.filter((id) => allowed.has(id));
});

async function submit() {
    if (groupId.value === null || !accountIds.value.length || isSaving.value) {
        return;
    }
    isSaving.value = true;
    error.value = "";
    try {
        const updated = await changeMembership(
            accountIds.value,
            [groupId.value],
            [],
        );
        visible.value = false;
        emit("updated", updated);
    } catch (e) {
        error.value = e instanceof Error ? e.message : String(e);
    } finally {
        isSaving.value = false;
    }
}
</script>

<template>
    <Dialog
        v-model:visible="visible"
        modal
        :draggable="false"
        :header="$gettext('Add Accounts to Group')"
        :style="{ width: '48rem' }"
    >
        <form
            class="add-accounts-form"
            @submit.prevent="submit"
        >
            <label for="abac-add-accounts-group">{{ $gettext("Group") }}</label>
            <Select
                v-model="groupId"
                input-id="abac-add-accounts-group"
                :options="groups"
                option-label="name"
                option-value="id"
                filter
                :placeholder="$gettext('Select a group…')"
            />
            <label for="abac-add-accounts-users">{{
                $gettext("Accounts")
            }}</label>
            <MultiSelect
                v-model="accountIds"
                input-id="abac-add-accounts-users"
                :options="candidates"
                option-label="label"
                option-value="id"
                display="chip"
                filter
                :disabled="groupId === null"
                :placeholder="$gettext('Select accounts…')"
                :empty-message="$gettext('Every account is already a member')"
            />
            <Message
                v-if="error"
                severity="error"
                role="alert"
            >
                {{ error }}
            </Message>
            <div class="actions">
                <Button
                    type="button"
                    severity="secondary"
                    :label="$gettext('Cancel')"
                    @click="visible = false"
                />
                <Button
                    type="submit"
                    :label="$gettext('Add')"
                    :disabled="groupId === null || !accountIds.length"
                    :loading="isSaving"
                />
            </div>
        </form>
    </Dialog>
</template>

<style scoped>
.add-accounts-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-size: 1.4rem;
}

.add-accounts-form label {
    font-weight: 600;
}

.actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.5rem;
}
</style>
