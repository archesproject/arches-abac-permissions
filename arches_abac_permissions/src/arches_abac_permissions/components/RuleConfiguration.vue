<script setup lang="ts">
import { computed } from "vue";
import { useGettext } from "vue3-gettext";

import InputText from "openvue/inputtext";
import Textarea from "openvue/textarea";

import RuleTypePicker from "@/arches_abac_permissions/components/RuleTypePicker.vue";
import LifecycleStateRuleForm from "@/arches_abac_permissions/components/rule_types/LifecycleStateRuleForm.vue";
import ResourceSetRuleForm from "@/arches_abac_permissions/components/rule_types/ResourceSetRuleForm.vue";
import {
    LIFECYCLE_STATE,
    RESOURCE_SET,
} from "@/arches_abac_permissions/constants.ts";

import type {
    ResourceModel,
    ResourceSet,
    RuleDraft,
    RuleTypeInfo,
} from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

const props = defineProps<{
    ruleTypes: RuleTypeInfo[];
    resourceModels: ResourceModel[];
    resourceSets: ResourceSet[];
}>();
const draft = defineModel<RuleDraft | null>({ required: true });
const emit = defineEmits<{ (e: "pick", ruleType: RuleTypeInfo): void }>();

// Add new rule types here with a form component taking v-model="definition".
const RULE_TYPE_FORMS = {
    [LIFECYCLE_STATE]: LifecycleStateRuleForm,
    [RESOURCE_SET]: ResourceSetRuleForm,
};

const ruleType = computed(() =>
    props.ruleTypes.find((type) => type.key === draft.value?.rule_type),
);
const form = computed(
    () =>
        RULE_TYPE_FORMS[
            (draft.value?.rule_type ?? "") as keyof typeof RULE_TYPE_FORMS
        ],
);
const formProps = computed(() =>
    draft.value?.rule_type === RESOURCE_SET
        ? { resourceSets: props.resourceSets }
        : { resourceModels: props.resourceModels },
);
const heading = computed(() => {
    if (!draft.value) {
        return "";
    }
    const label = ruleType.value?.label ?? "";
    return draft.value.id
        ? $gettext("Edit rule: %{name}", { name: draft.value.name })
        : $gettext("New rule: %{label}", { label });
});
</script>

<template>
    <section
        class="column"
        :aria-label="$gettext('Rule Configuration')"
    >
        <header class="column-header">
            <h2 class="column-title">
                <i
                    class="pi pi-sliders-h"
                    aria-hidden="true"
                ></i>
                {{ $gettext("Rule Configuration") }}
            </h2>
        </header>
        <div class="column-body">
            <RuleTypePicker
                v-if="!draft"
                :rule-types="ruleTypes"
                @pick="emit('pick', $event)"
            />
            <form
                v-else
                class="rule-form"
                @submit.prevent
            >
                <h3 class="form-heading">{{ heading }}</h3>
                <div class="field">
                    <label for="abac-rule-name">{{
                        $gettext("Rule Name")
                    }}</label>
                    <InputText
                        id="abac-rule-name"
                        v-model="draft.name"
                        maxlength="255"
                        required
                        :placeholder="$gettext('Enter rule name…')"
                    />
                </div>
                <div class="field">
                    <label for="abac-rule-description">{{
                        $gettext("Description")
                    }}</label>
                    <Textarea
                        id="abac-rule-description"
                        v-model="draft.description"
                        rows="3"
                        auto-resize
                        :placeholder="$gettext('Describe this rule…')"
                    />
                </div>
                <component
                    :is="form"
                    v-if="form"
                    v-model="draft.definition"
                    v-bind="formProps"
                />
            </form>
        </div>
    </section>
</template>

<style scoped>
.column-body {
    flex: 1;
    overflow-y: auto;
}

.rule-form {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 2.4rem 2.8rem;
}

.form-heading {
    margin: 0;
    font-size: 1.8rem;
    font-weight: 500;
    color: var(--abac-text-primary);
}
</style>
