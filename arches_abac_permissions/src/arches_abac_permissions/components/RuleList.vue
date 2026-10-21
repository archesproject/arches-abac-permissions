<script setup lang="ts">
import { computed, ref } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import InputText from "openvue/inputtext";

import {
    groupNamesForRule,
    ruleMatchesFilter,
} from "@/arches_abac_permissions/utils.ts";

import type {
    Group,
    Rule,
    RuleTypeInfo,
} from "@/arches_abac_permissions/types";

const MAX_VISIBLE_GROUPS = 2;

const { $gettext } = useGettext();

const props = defineProps<{
    rules: Rule[];
    groups: Group[];
    ruleTypes: RuleTypeInfo[];
    selectedId: string | null;
}>();

const emit = defineEmits<{
    (e: "select", rule: Rule): void;
    (e: "add"): void;
    (e: "delete", rule: Rule): void;
}>();

const filter = ref("");

const groupsById = computed(
    () => new Map(props.groups.map((group) => [group.id, group])),
);

function typeLabel(rule: Rule) {
    return (
        props.ruleTypes.find((type) => type.key === rule.rule_type)?.label ?? ""
    );
}

const rows = computed(() =>
    props.rules
        .map((rule) => ({
            rule,
            typeLabel: typeLabel(rule),
            groupNames: groupNamesForRule(rule, groupsById.value),
        }))
        .filter((row) =>
            ruleMatchesFilter(
                row.rule,
                filter.value,
                row.typeLabel,
                row.groupNames,
            ),
        ),
);
</script>

<template>
    <section
        class="column"
        :aria-label="$gettext('Rules')"
    >
        <header class="column-header">
            <h2 class="column-title">
                <i
                    class="pi pi-filter"
                    aria-hidden="true"
                ></i>
                {{ $gettext("Rules") }}
                <span class="count">{{ rules.length }}</span>
            </h2>
        </header>
        <div class="toolbar">
            <InputText
                v-model="filter"
                type="search"
                size="small"
                class="filter-input"
                :placeholder="$gettext('Filter rules…')"
                :aria-label="$gettext('Filter rules')"
            />
            <Button
                size="small"
                icon="pi pi-plus"
                :label="$gettext('Add Rule')"
                @click="emit('add')"
            />
        </div>
        <ul class="rule-list">
            <li
                v-if="rows.length === 0"
                class="empty"
            >
                {{
                    rules.length === 0
                        ? $gettext("No rules yet")
                        : $gettext("No rules match the filter")
                }}
            </li>
            <li
                v-for="row in rows"
                :key="row.rule.id"
                class="rule-row"
                :class="{ selected: row.rule.id === selectedId }"
            >
                <button
                    type="button"
                    class="rule-select"
                    :aria-current="
                        row.rule.id === selectedId ? 'true' : undefined
                    "
                    @click="emit('select', row.rule)"
                >
                    <span class="rule-name">{{ row.rule.name }}</span>
                    <span class="badges">
                        <span
                            class="badge"
                            :class="
                                row.rule.active
                                    ? 'badge-active'
                                    : 'badge-inactive'
                            "
                        >
                            {{
                                row.rule.active
                                    ? $gettext("Active")
                                    : $gettext("Inactive")
                            }}
                        </span>
                        <span class="badge badge-type">{{
                            row.typeLabel
                        }}</span>
                    </span>
                    <span class="rule-groups">
                        <template v-if="row.groupNames.length === 0">
                            <em>{{ $gettext("No groups assigned") }}</em>
                        </template>
                        <template v-else>
                            {{
                                row.groupNames
                                    .slice(0, MAX_VISIBLE_GROUPS)
                                    .join(", ")
                            }}
                            <span
                                v-if="
                                    row.groupNames.length > MAX_VISIBLE_GROUPS
                                "
                            >
                                {{
                                    $gettext("+%{ count } more", {
                                        count: String(
                                            row.groupNames.length -
                                                MAX_VISIBLE_GROUPS,
                                        ),
                                    })
                                }}
                            </span>
                        </template>
                    </span>
                </button>
                <Button
                    class="delete-button"
                    icon="pi pi-trash"
                    severity="danger"
                    variant="text"
                    size="small"
                    :aria-label="
                        $gettext('Delete rule %{ name }', {
                            name: row.rule.name,
                        })
                    "
                    @click="emit('delete', row.rule)"
                />
            </li>
        </ul>
    </section>
</template>

<style scoped>
.filter-input {
    flex: 1;
    min-width: 0;
}

.count {
    font-weight: 400;
    color: var(--p-text-muted-color);
}

.rule-list {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    flex: 1;
}

.rule-row {
    display: flex;
    align-items: flex-start;
    border-bottom: 1px solid var(--p-content-border-color);
}

.rule-row.selected {
    background: var(--p-highlight-background);
}

.rule-select {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 0.75rem 1rem;
    border: none;
    background: none;
    text-align: left;
    cursor: pointer;
    color: inherit;
    font: inherit;
}

.rule-select:hover {
    background: var(--p-content-hover-background);
}

.rule-select:focus-visible {
    outline: 2px solid var(--p-primary-color);
    outline-offset: -2px;
}

.rule-name {
    font-weight: 600;
    overflow-wrap: anywhere;
}

.badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
}

.badge {
    padding: 0.1rem 0.5rem;
    border-radius: 1rem;
    font-size: 1.1rem;
    border: 1px solid var(--p-content-border-color);
}

.badge-active {
    color: var(--p-green-800);
    background: var(--p-green-100);
}

.badge-inactive {
    color: var(--p-text-muted-color);
    background: var(--p-surface-100);
}

.rule-groups {
    font-size: 1.2rem;
    color: var(--p-text-muted-color);
}

.delete-button {
    margin: 0.5rem 0.5rem 0 0;
}
</style>
