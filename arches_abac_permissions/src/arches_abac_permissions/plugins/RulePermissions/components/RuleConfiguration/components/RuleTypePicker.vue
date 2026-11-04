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
                    <span
                        class="type-icon"
                        aria-hidden="true"
                    >
                        <i :class="ruleType.icon"></i>
                    </span>
                    <span class="type-body">
                        <span class="type-kicker">{{
                            $gettext("Add new rule")
                        }}</span>
                        <span class="type-title">{{ ruleType.label }}</span>
                        <span class="type-description">{{
                            ruleType.description
                        }}</span>
                    </span>
                </button>
            </li>
        </ul>
    </div>
</template>

<style scoped>
.picker {
    padding: 2.8rem 3.2rem;
}

.prompt {
    margin: 0 0 1rem;
    font-size: 1.6rem;
    color: var(--abac-text-secondary);
}

.type-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(30rem, 1fr));
    gap: 1.4rem;
}

.type-card {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.4rem;
    padding: 4rem 2.2rem 6rem;
    border: 1px solid var(--abac-border);
    border-radius: 1rem;
    background: var(--abac-surface-card);
    color: var(--abac-text-primary);
    font: inherit;
    text-align: center;
    cursor: pointer;
    transition:
        background 0.12s,
        border-color 0.12s;
}

.type-card:hover {
    border-color: var(--abac-accent);
    background: var(--abac-row-hover);
}

.type-card:focus-visible {
    outline: 2px solid var(--abac-accent);
    outline-offset: 2px;
}

.type-icon {
    width: 4.8rem;
    height: 4.8rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--abac-border);
    border-radius: 1rem;
    background: var(--abac-surface-bg);
    color: var(--abac-accent);
    font-size: 2rem;
}

.type-icon i {
    font-size: inherit;
}

.type-body {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
}

.type-kicker {
    font-size: 1.6rem;
    color: var(--abac-text-secondary);
}

.type-title {
    font-size: 1.8rem;
    font-weight: 700;
}

.type-description {
    font-size: 1.25rem;
    line-height: 1.55;
    color: var(--abac-text-secondary);
}
</style>
