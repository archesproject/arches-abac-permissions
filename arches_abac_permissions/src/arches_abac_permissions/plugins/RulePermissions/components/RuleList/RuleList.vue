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
const noGroupsLabel = $gettext("<no groups assigned>");

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

function typeLabel(rule: Rule): string {
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
                <span class="count">{{
                    filter ? `${rows.length} of ${rules.length}` : rules.length
                }}</span>
            </h2>
            <InputText
                v-model="filter"
                type="search"
                class="header-filter"
                :placeholder="$gettext('Filter rules…')"
                :aria-label="$gettext('Filter rules')"
            />
            <Button
                class="toolbar-actions"
                icon="pi pi-plus"
                :label="$gettext('Add Rule')"
                @click="emit('add')"
            />
        </header>
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
                    <i
                        class="pi pi-filter row-icon"
                        aria-hidden="true"
                    ></i>
                    <span class="rule-body">
                        <span class="rule-name">{{ row.rule.name }}</span>
                        <span class="badges">
                            <span
                                class="status-badge"
                                :class="{ 'status-active': row.rule.active }"
                            >
                                {{
                                    row.rule.active
                                        ? $gettext("Active")
                                        : $gettext("Inactive")
                                }}
                            </span>
                            <span class="type-badge">{{ row.typeLabel }}</span>
                        </span>
                        <span class="groups-line">
                            <span
                                class="rule-groups"
                                :class="{ none: row.groupNames.length === 0 }"
                            >
                                {{
                                    row.groupNames.length === 0
                                        ? noGroupsLabel
                                        : row.groupNames
                                              .slice(0, MAX_VISIBLE_GROUPS)
                                              .join(", ")
                                }}
                            </span>
                            <span
                                v-if="
                                    row.groupNames.length > MAX_VISIBLE_GROUPS
                                "
                                class="more-pill"
                            >
                                {{
                                    $gettext("+%{count} more", {
                                        count: String(
                                            row.groupNames.length -
                                                MAX_VISIBLE_GROUPS,
                                        ),
                                    })
                                }}
                            </span>
                        </span>
                    </span>
                </button>
                <button
                    type="button"
                    class="row-delete"
                    :title="$gettext('Delete rule')"
                    :aria-label="
                        $gettext('Delete rule %{name}', {
                            name: row.rule.name,
                        })
                    "
                    @click="emit('delete', row.rule)"
                >
                    <i
                        class="pi pi-trash"
                        aria-hidden="true"
                    ></i>
                </button>
            </li>
        </ul>
    </section>
</template>

<style scoped>
.header-filter {
    max-inline-size: 18rem;
}

.rule-list {
    list-style: none;
    margin: 0;
    padding: 0 0.5rem;
    overflow-y: auto;
    flex: 1;
}

.rule-row {
    display: flex;
    align-items: flex-start;
    gap: 0.4rem;
    padding-inline-end: 0.8rem;
    border-block-end: 0.1rem solid var(--p-abac-border);
    background: var(--p-abac-surface-card);
    color: var(--p-abac-text-primary);
}

.rule-row:hover {
    background: var(--p-abac-row-hover);
}

.rule-row.selected {
    background: var(--p-abac-accent-subtle);
    color: var(--p-abac-brand-light);
}

.rule-row .row-delete {
    margin-block-start: 0.7rem;
}

.rule-select {
    flex: 1;
    min-inline-size: 0;
    display: flex;
    align-items: flex-start;
    gap: 0.8rem;
    padding-block: 0.9rem;
    padding-inline: 1.2rem 0;
    border: none;
    background: none;
    text-align: start;
    cursor: pointer;
    color: inherit;
    font: inherit;
}

.rule-select:focus-visible {
    outline: 0.2rem solid var(--p-abac-accent);
    outline-offset: -0.2rem;
}

.row-icon {
    margin-block-start: 0.3rem;
    font-size: 1.3rem;
    color: var(--p-abac-text-secondary);
}

.rule-row.selected .row-icon {
    color: var(--p-abac-brand-light);
}

.rule-body {
    flex: 1;
    min-inline-size: 0;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
}

.rule-name {
    font-size: 1.35rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.rule-row.selected .rule-name {
    font-weight: 600;
}

.badges,
.groups-line {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    min-inline-size: 0;
}

.groups-line {
    gap: 0.6rem;
}

.type-badge {
    flex-shrink: 0;
    padding: 0.1rem 0.8rem;
    border: 0.1rem solid
        color-mix(in srgb, var(--p-abac-accent) 25%, transparent);
    border-radius: 1rem;
    background: var(--p-abac-accent-tint);
    color: var(--p-abac-accent);
    font-size: 1.1rem;
    font-weight: 600;
    white-space: nowrap;
}

.rule-row.selected .type-badge {
    color: var(--p-abac-brand-light);
    background: color-mix(in srgb, var(--p-abac-brand-light) 12%, transparent);
    border-color: color-mix(
        in srgb,
        var(--p-abac-brand-light) 30%,
        transparent
    );
}

.rule-groups {
    font-size: 1.2rem;
    color: var(--p-abac-text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.rule-groups.none {
    font-style: italic;
}
</style>
