<script setup lang="ts">
import { useGettext } from "vue3-gettext";

const { $gettext } = useGettext();

defineProps<{
    isBuiltIn?: boolean;
    isPublic?: boolean;
}>();
</script>

<template>
    <span
        v-if="isBuiltIn"
        class="group-flag"
        :title="$gettext('Created by Arches; cannot be deleted')"
        >{{ $gettext("Built-in") }}</span
    >
    <span
        v-if="isPublic"
        class="group-flag public"
        :title="$gettext('Applies to visitors who are not logged in')"
    >
        <i
            class="pi pi-globe"
            aria-hidden="true"
        ></i>
        {{ $gettext("Public") }}
    </span>
</template>

<style scoped>
.group-flag {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
    padding: 0.1rem 0.6rem;
    border: 0.1rem solid var(--p-abac-border);
    border-radius: 1rem;
    background: var(--p-abac-surface-bg);
    color: var(--p-abac-text-secondary);
    font-size: 1.1rem;
    font-weight: 600;
    white-space: nowrap;
}

.group-flag.public {
    border-color: var(--p-abac-warning-border);
    background: var(--p-abac-warning-bg);
    color: var(--p-abac-warning-text);
}

.group-flag .pi {
    font-size: 1rem;
}
</style>
