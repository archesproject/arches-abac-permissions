<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Dialog from "openvue/dialog";
import Message from "openvue/message";
import MultiSelect from "openvue/multiselect";
import Select from "openvue/select";

import { changeMembership } from "@/arches_abac_permissions/api.ts";
import { userDisplayName } from "@/arches_abac_permissions/utils.ts";

import type { User, Group } from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

const visible = defineModel<boolean>("visible", { required: true });
const props = defineProps<{
    groups: Group[];
    users: User[];
    initialGroupId: number | null;
}>();
const emit = defineEmits<{ (e: "updated", users: User[]): void }>();

const groupId = ref<number | null>(null);
const userIds = ref<number[]>([]);
const error = ref("");
const isSaving = ref(false);

// Only users not already in the chosen group.
const candidates = computed(() =>
    props.users
        .filter(
            (user) =>
                groupId.value === null || !user.groups.includes(groupId.value),
        )
        .map((user) => ({
            id: user.id,
            label: `${userDisplayName(user)} (@${user.username})`,
        })),
);

watch(visible, (isVisible) => {
    if (isVisible) {
        groupId.value = props.initialGroupId;
        userIds.value = [];
        error.value = "";
    }
});

watch(groupId, () => {
    const allowed = new Set(candidates.value.map((c) => c.id));
    userIds.value = userIds.value.filter((id) => allowed.has(id));
});

async function submit(): Promise<void> {
    if (groupId.value === null || !userIds.value.length || isSaving.value) {
        return;
    }
    isSaving.value = true;
    error.value = "";
    try {
        const updated = await changeMembership(
            userIds.value,
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
        :modal="true"
        :draggable="false"
        :header="$gettext('Add Users to Group')"
        class="abac-add-users-dialog"
    >
        <form
            class="add-users-form"
            @submit.prevent="submit"
        >
            <label for="abac-add-users-group">{{ $gettext("Group") }}</label>
            <Select
                v-model="groupId"
                input-id="abac-add-users-group"
                :options="groups"
                option-label="name"
                option-value="id"
                :filter="true"
                :placeholder="$gettext('Select a group…')"
            />
            <label for="abac-add-users-select">{{ $gettext("Users") }}</label>
            <MultiSelect
                v-model="userIds"
                input-id="abac-add-users-select"
                :options="candidates"
                option-label="label"
                option-value="id"
                display="chip"
                :filter="true"
                :disabled="groupId === null"
                :placeholder="$gettext('Select users…')"
                :empty-message="$gettext('Every user is already a member')"
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
                    :disabled="groupId === null || !userIds.length"
                    :loading="isSaving"
                />
            </div>
        </form>
    </Dialog>
</template>

<style>
/* Unscoped: Dialog is teleported out of this component. */
.abac-add-users-dialog {
    inline-size: 48rem;
}
</style>

<style scoped>
.add-users-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-size: 1.4rem;
}

.add-users-form label {
    font-weight: 600;
}

.actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-block-start: 0.5rem;
}
</style>
