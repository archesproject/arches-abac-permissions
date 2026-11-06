<script setup lang="ts">
import { ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Dialog from "openvue/dialog";
import InputText from "openvue/inputtext";
import Message from "openvue/message";

import { createGroup } from "@/arches_abac_permissions/api.ts";

import type { Group } from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

const visible = defineModel<boolean>("visible", { required: true });
const emit = defineEmits<{ (e: "created", group: Group): void }>();

const name = ref("");
const error = ref("");
const isSaving = ref(false);

watch(visible, (isVisible) => {
    if (isVisible) {
        name.value = "";
        error.value = "";
    }
});

async function submit(): Promise<void> {
    if (!name.value.trim() || isSaving.value) {
        return;
    }
    isSaving.value = true;
    error.value = "";
    try {
        const group = await createGroup(name.value.trim());
        visible.value = false;
        emit("created", group);
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
        :header="$gettext('Add Group')"
        class="abac-add-group-dialog"
    >
        <form
            class="add-group-form"
            @submit.prevent="submit"
        >
            <label for="abac-new-group-name">{{
                $gettext("Group name")
            }}</label>
            <InputText
                id="abac-new-group-name"
                v-model="name"
                maxlength="150"
                :autofocus="true"
                :invalid="Boolean(error)"
                :aria-describedby="error ? 'abac-new-group-error' : undefined"
            />
            <Message
                v-if="error"
                id="abac-new-group-error"
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
                    :label="$gettext('Add Group')"
                    :disabled="!name.trim()"
                    :loading="isSaving"
                />
            </div>
        </form>
    </Dialog>
</template>

<style>
/* Unscoped: Dialog is teleported out of this component. */
.abac-add-group-dialog {
    inline-size: 40rem;
}
</style>

<style scoped>
.add-group-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.add-group-form label {
    font-weight: 600;
}

.actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-block-start: 0.5rem;
}
</style>
