<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import MultiSelect from "openvue/multiselect";

import { nestedGroupIds } from "@/arches_abac_permissions/utils.ts";

import type { Group } from "@/arches_abac_permissions/types";

const UPDATE_PARENTS_EVENT = "update-parents" as const;

const props = defineProps<{
    groupId: number;
    groupName: string;
    parentIds: number[];
    inheritsFromIds: number[];
    groups: Group[];
    saving: boolean;
}>();

const emit = defineEmits<{
    (event: typeof UPDATE_PARENTS_EVENT, parentIds: number[]): void;
}>();

const { $gettext } = useGettext();

const selected = ref<number[]>([...props.parentIds]);

// A group can't sit inside itself or a group inside it.
const options = computed(() => {
    const nested = nestedGroupIds(props.groups, props.groupId);
    return props.groups.filter(
        (group) => group.id !== props.groupId && !nested.has(group.id),
    );
});
// In the server's order: nearest group first, following the inheritance.
const inheritsFromNames = computed(() => {
    const names = [];
    for (const groupId of props.inheritsFromIds) {
        const group = props.groups.find(
            (candidate) => candidate.id === groupId,
        );
        if (group) {
            names.push(group.name);
        }
    }
    return names;
});
const inputId = computed(() => `abac-parent-groups-${props.groupId}`);

// Once a save finishes, show what was saved, including after a refused one.
watch(
    () => [props.parentIds, props.saving] as const,
    ([parentIds, saving]) => {
        if (!saving) {
            selected.value = [...parentIds];
        }
    },
);

function updateParents(parentIds: number[]): void {
    selected.value = parentIds;
    emit(UPDATE_PARENTS_EVENT, parentIds);
}
</script>

<template>
    <div class="parent-groups-editor">
        <label :for="inputId">
            {{ $gettext("%{group} sits inside", { group: groupName }) }}
        </label>
        <MultiSelect
            :input-id="inputId"
            :model-value="selected"
            :options="options"
            option-label="name"
            option-value="id"
            display="chip"
            :filter="true"
            :disabled="saving"
            :placeholder="$gettext('No parent groups')"
            @update:model-value="updateParents"
        />
        <div
            v-if="inheritsFromNames.length > 0"
            class="inherits-from"
        >
            <span class="inherits-from-label">{{
                $gettext("Members also get the rules of:")
            }}</span>
            <span>{{ inheritsFromNames.join(", ") }}</span>
        </div>
    </div>
</template>

<style scoped>
.parent-groups-editor {
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    gap: 0.8rem;
    min-block-size: 28rem;
    min-inline-size: 0;
    padding: 1.2rem 1.6rem;
    border-block-start: 0.1rem solid var(--p-abac-border);
    font-size: 1.4rem;
    color: var(--p-abac-text-primary);
}

.parent-groups-editor label {
    font-weight: 600;
}

.parent-groups-editor .inherits-from {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    color: var(--p-abac-brand-light);
}

.parent-groups-editor .inherits-from-label {
    font-weight: 600;
}

.parent-groups-editor :deep(.p-multiselect) {
    inline-size: 100%;
}

/* Matches GroupMembership's stacked layout (rem ignores Arches' 62.5% root here). */
@media (max-width: 75rem) {
    .parent-groups-editor {
        min-block-size: 22rem;
    }
}

/* Chips wrap onto new lines instead of widening the panel. */
.parent-groups-editor :deep(.p-multiselect-label) {
    flex-wrap: wrap;
    white-space: normal;
}
</style>
