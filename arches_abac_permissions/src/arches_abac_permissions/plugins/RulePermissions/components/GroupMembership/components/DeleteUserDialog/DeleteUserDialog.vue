<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import Dialog from "openvue/dialog";
import InputText from "openvue/inputtext";
import Message from "openvue/message";

import { userDisplayName } from "@/arches_abac_permissions/utils.ts";

import type { User, UserDetails } from "@/arches_abac_permissions/types";

const props = defineProps<{
    user: User | null;
    details: UserDetails | null;
    groupNames: string[];
    isDeleting: boolean;
}>();
const emit = defineEmits<{
    (e: "close"): void;
    (e: "delete", user: User): void;
    (e: "deactivate", user: User): void;
}>();

const { $gettext } = useGettext();

const confirmText = ref("");

const isVisible = computed({
    get: () => props.user !== null,
    set: (visible: boolean) => {
        if (!visible) {
            emit("close");
        }
    },
});
const isBlocked = computed(() => props.details?.can_delete === false);
const canDeactivate = computed(() => Boolean(props.user?.is_active));
const isConfirmed = computed(
    () =>
        props.details?.can_delete === true &&
        confirmText.value.trim() === props.user?.username,
);

watch(
    () => props.user?.id,
    () => (confirmText.value = ""),
);

function confirmDelete(): void {
    if (props.user && isConfirmed.value && !props.isDeleting) {
        emit("delete", props.user);
    }
}
</script>

<template>
    <Dialog
        v-model:visible="isVisible"
        modal
        role="alertdialog"
        class="abac-delete-user-dialog"
        :draggable="false"
        :header="
            user
                ? $gettext('Delete %{name}?', { name: userDisplayName(user) })
                : ''
        "
    >
        <form
            v-if="user"
            class="delete-user"
            @submit.prevent="confirmDelete"
        >
            <p class="delete-copy">
                {{ $gettext("This permanently removes") }}
                <strong class="username">@{{ user.username }}</strong
                >. {{ $gettext("It can’t be undone.") }}
            </p>
            <Message
                v-if="isBlocked"
                severity="warn"
                role="alert"
            >
                {{ details?.delete_block_reason }}
            </Message>
            <div class="consequences">
                <p class="delete-copy">
                    {{ $gettext("Deleting this account will result in:") }}
                </p>
                <ul>
                    <li v-if="groupNames.length">
                        {{
                            $gettext(
                                "Removal from %{count} group(s) (%{names})",
                                {
                                    count: String(groupNames.length),
                                    names: groupNames.join(", "),
                                },
                            )
                        }}
                    </li>
                    <li v-else>{{ $gettext("Not a member of any groups") }}</li>
                    <li>{{ $gettext("Can no longer sign in") }}</li>
                    <li>
                        {{
                            $gettext(
                                "Edits they made keep their history, but will no longer link to an account",
                            )
                        }}
                    </li>
                </ul>
            </div>
            <div
                v-if="canDeactivate"
                class="deactivate-note"
            >
                <i
                    class="pi pi-info-circle"
                    aria-hidden="true"
                ></i>
                <span>
                    <strong>{{
                        $gettext("Just need to block access?")
                    }}</strong>
                    {{
                        $gettext(
                            "Deactivate the account instead. That can be reversed.",
                        )
                    }}
                </span>
                <Button
                    type="button"
                    size="small"
                    :severity="isBlocked ? 'primary' : 'secondary'"
                    :label="$gettext('Deactivate')"
                    @click="emit('deactivate', user)"
                />
            </div>
            <div class="confirm-field">
                <label for="abac-delete-confirm">
                    {{ $gettext("Type") }}
                    <strong class="username">{{ user.username }}</strong>
                    {{ $gettext("to confirm") }}
                </label>
                <InputText
                    id="abac-delete-confirm"
                    v-model="confirmText"
                    class="username"
                    autocomplete="off"
                    spellcheck="false"
                    :disabled="!details || isBlocked"
                />
            </div>
            <div class="actions">
                <Button
                    type="button"
                    severity="secondary"
                    :label="$gettext('Cancel')"
                    @click="isVisible = false"
                />
                <Button
                    type="submit"
                    severity="danger"
                    icon="pi pi-trash"
                    :label="$gettext('Delete account')"
                    :disabled="!isConfirmed"
                    :loading="isDeleting"
                />
            </div>
        </form>
    </Dialog>
</template>

<style>
/* Unscoped: Dialog is teleported out of this component. */
.abac-delete-user-dialog {
    inline-size: 48rem;
}
</style>

<style scoped>
.delete-user {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
}

.delete-copy {
    margin: 0;
    color: var(--p-abac-text-secondary);
}

.username {
    font-family: monospace;
    color: var(--p-abac-text-primary);
}

.consequences {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
}

.consequences ul {
    margin: 0;
    padding-inline-start: 2rem;
    color: var(--p-abac-text-secondary);
}

.deactivate-note {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.9rem 1.1rem;
    border: 0.1rem solid
        color-mix(in srgb, var(--p-abac-accent) 30%, transparent);
    border-radius: 0.6rem;
    background: var(--p-abac-accent-tint);
}

.deactivate-note > span {
    flex: 1;
}

.deactivate-note .pi {
    color: var(--p-abac-accent);
}

.confirm-field {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
}

.actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.8rem;
}
</style>
