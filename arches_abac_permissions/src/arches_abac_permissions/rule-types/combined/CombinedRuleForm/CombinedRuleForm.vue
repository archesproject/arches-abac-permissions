<script setup lang="ts">
import { computed, ref, watchEffect } from "vue";
import { useGettext } from "vue3-gettext";

import { useToast } from "openvue/usetoast";

import RuleGroup from "@/arches_abac_permissions/rule-types/combined/CombinedRuleForm/components/RuleGroup/RuleGroup.vue";

import { fetchRules } from "@/arches_abac_permissions/api.ts";
import {
    DEFAULT_ERROR_TOAST_LIFE,
    ERROR,
} from "@/arches_abac_permissions/constants.ts";
import { toGroup } from "@/arches_abac_permissions/rule-types/combined/group.ts";

import type {
    CombinedDefinition,
    CombinedGroup,
    RuleOption,
} from "@/arches_abac_permissions/rule-types/combined/types";
import type { Rule } from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();
const toast = useToast();

const definition = defineModel<Partial<CombinedDefinition>>({
    required: true,
});
const rules = ref<Rule[]>([]);
const isLoading = ref(true);

const group = computed((): CombinedGroup => toGroup(definition.value));
const ruleOptions = computed((): RuleOption[] =>
    rules.value.map(({ id, name }) => ({ id, label: name })),
);

watchEffect(loadRules);

function onGroupChange(changed: CombinedGroup): void {
    definition.value = changed;
}

async function loadRules(): Promise<void> {
    try {
        rules.value = await fetchRules();
    } catch (error) {
        toast.add({
            severity: ERROR,
            life: DEFAULT_ERROR_TOAST_LIFE,
            summary: $gettext("Unable to load rules"),
            detail: error instanceof Error ? error.message : undefined,
        });
    } finally {
        isLoading.value = false;
    }
}
</script>

<template>
    <RuleGroup
        input-id="abac-combined"
        :model-value="group"
        :rule-options="ruleOptions"
        :is-loading="isLoading"
        :is-nested="false"
        @update:model-value="onGroupChange"
    />
</template>
