<script setup lang="ts">
import { useGettext } from "vue3-gettext";

import type { RuleTypeInfo } from "@/arches_abac_permissions/types";

const { $gettext } = useGettext();

defineProps<{ ruleTypes: RuleTypeInfo[] }>();
const emit = defineEmits<{ (e: "pick", ruleType: RuleTypeInfo): void }>();
</script>

<template>
    <div class="picker">
        <p class="prompt">
            {{
                $gettext(
                    "Select a rule from the list, or create a new rule of one of the following types:",
                )
            }}
        </p>
        <ul class="type-list">
            <li
                v-for="ruleType in ruleTypes"
                :key="ruleType.key"
            >
                <button
                    type="button"
                    class="type-card"
                    @click="emit('pick', ruleType)"
                >
                    <i
                        :class="ruleType.icon"
                        class="type-icon"
                        aria-hidden="true"
                    ></i>
                    <span class="type-body">
                        <span class="muted">{{
                            $gettext("Add new rule")
                        }}</span>
                        <span class="type-title">{{ ruleType.label }}</span>
                        <span class="muted">{{ ruleType.description }}</span>
                    </span>
                </button>
            </li>
        </ul>
    </div>
</template>

<style scoped>
.picker {
    padding: 2rem;
}

.prompt {
    margin: 0 0 1.5rem;
    color: var(--p-text-muted-color);
}

.type-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    max-width: 60rem;
}

.type-card {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 1.25rem 1.5rem;
    border: 1px solid var(--p-content-border-color);
    border-radius: 0.5rem;
    background: var(--p-content-background);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
}

.type-card:hover {
    border-color: var(--p-primary-color);
    background: var(--p-content-hover-background);
}

.type-card:focus-visible {
    outline: 2px solid var(--p-primary-color);
    outline-offset: 2px;
}

.type-icon {
    font-size: 2.4rem;
    color: var(--p-primary-color);
}

.type-body {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.type-title {
    font-size: 1.6rem;
    font-weight: 600;
}

.muted {
    color: var(--p-text-muted-color);
}
</style>
