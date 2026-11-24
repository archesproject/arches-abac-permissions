<script setup lang="ts">
import { computed } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import MultiSelect from "openvue/multiselect";
import Select from "openvue/select";

import { toGroup } from "@/arches_abac_permissions/rule-types/combined/group.ts";

import type {
    CombinedGroup,
    CombinedOperator,
    RuleOption,
} from "@/arches_abac_permissions/rule-types/combined/types";

const REMOVE_EVENT = "remove" as const;

const { inputId, ruleOptions, isLoading, isNested } = defineProps<{
    inputId: string;
    ruleOptions: RuleOption[];
    isLoading: boolean;
    isNested: boolean;
}>();
const emit = defineEmits<{ (event: typeof REMOVE_EVENT): void }>();

const { $gettext } = useGettext();

const group = defineModel<CombinedGroup>({ required: true });

const operatorOptions = computed(
    (): { value: CombinedOperator; label: string }[] => [
        { value: "or", label: $gettext("Matched by any of") },
        { value: "and", label: $gettext("Matched by all of") },
    ],
);

function update(changes: Partial<CombinedGroup>): void {
    group.value = { ...group.value, ...changes };
}

function onGroupChange(index: number, child: CombinedGroup): void {
    update({
        groups: group.value.groups.map((existing, position) =>
            position === index ? child : existing,
        ),
    });
}

function addGroup(): void {
    update({ groups: [...group.value.groups, toGroup({})] });
}

function removeGroup(index: number): void {
    update({
        groups: group.value.groups.filter((_, position) => position !== index),
    });
}
</script>

<template>
    <div
        class="rule-group"
        :class="{ nested: isNested }"
    >
        <div class="field">
            <label :for="`${inputId}-operator`">{{ $gettext("Match") }}</label>
            <div class="operator-row">
                <Select
                    option-label="label"
                    option-value="value"
                    :input-id="`${inputId}-operator`"
                    :model-value="group.operator"
                    :options="operatorOptions"
                    @update:model-value="
                        (operator: CombinedOperator) => update({ operator })
                    "
                />
                <Button
                    v-if="isNested"
                    size="small"
                    severity="secondary"
                    variant="text"
                    icon="pi pi-trash"
                    :aria-label="$gettext('Remove group')"
                    @click="emit(REMOVE_EVENT)"
                />
            </div>
        </div>
        <div class="field">
            <label :for="`${inputId}-rules`">{{ $gettext("Rules") }}</label>
            <MultiSelect
                display="chip"
                option-label="label"
                option-value="id"
                :input-id="`${inputId}-rules`"
                :model-value="group.rule_ids"
                :options="ruleOptions"
                :loading="isLoading"
                :filter="true"
                :placeholder="$gettext('Select rules…')"
                @update:model-value="
                    (ruleIds: string[] | null) =>
                        update({ rule_ids: ruleIds ?? [] })
                "
            />
        </div>
        <RuleGroup
            v-for="(child, index) in group.groups"
            :key="index"
            :input-id="`${inputId}-${index}`"
            :model-value="child"
            :rule-options="ruleOptions"
            :is-loading="isLoading"
            :is-nested="true"
            @update:model-value="
                (value: CombinedGroup) => onGroupChange(index, value)
            "
            @remove="removeGroup(index)"
        />
        <div>
            <Button
                size="small"
                severity="secondary"
                variant="outlined"
                icon="pi pi-plus"
                :label="$gettext('Add group')"
                @click="addGroup"
            />
        </div>
        <div class="field">
            <label :for="`${inputId}-exclude`">{{
                $gettext("Except resources matched by")
            }}</label>
            <MultiSelect
                display="chip"
                option-label="label"
                option-value="id"
                :input-id="`${inputId}-exclude`"
                :model-value="group.exclude_rule_ids"
                :options="ruleOptions"
                :loading="isLoading"
                :filter="true"
                :placeholder="$gettext('Optional')"
                @update:model-value="
                    (ruleIds: string[] | null) =>
                        update({ exclude_rule_ids: ruleIds ?? [] })
                "
            />
        </div>
    </div>
</template>

<style scoped>
.rule-group {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.rule-group.nested {
    border-inline-start: 0.125rem solid var(--p-content-border-color);
    padding-inline-start: 1rem;
}

.rule-group .operator-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}
</style>
