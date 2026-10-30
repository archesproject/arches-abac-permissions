<script setup lang="ts">
import { ref } from "vue";
import { useGettext } from "vue3-gettext";

const { $gettext } = useGettext();

const props = defineProps<{
    // Undefined until the rule has been saved.
    indexSql?: string | null;
    isStale: boolean;
}>();

const copyStatus = ref("");

async function copy() {
    try {
        await navigator.clipboard.writeText(props.indexSql ?? "");
        copyStatus.value = $gettext("Copied");
    } catch {
        copyStatus.value = $gettext("Unable to copy");
    }
}
</script>

<template>
    <details class="index-sql">
        <summary>
            <i
                class="pi pi-database"
                aria-hidden="true"
            ></i>
            {{ $gettext("Index SQL") }}
        </summary>
        <div class="index-sql-body">
            <p v-if="indexSql === undefined">
                {{ $gettext("Save the rule to see the SQL for its index.") }}
            </p>
            <p v-else-if="indexSql === null">
                {{ $gettext("This rule doesn't need an additional index.") }}
            </p>
            <template v-else>
                <p>
                    {{
                        $gettext(
                            "Run this SQL against the Arches database to speed up evaluating this rule. CONCURRENTLY can't run inside a transaction.",
                        )
                    }}
                </p>
                <pre><code>{{ indexSql }}</code></pre>
                <span class="copy-row">
                    <button
                        type="button"
                        class="copy-button"
                        @click="copy"
                    >
                        <i
                            class="pi pi-copy"
                            aria-hidden="true"
                        ></i>
                        {{ $gettext("Copy SQL") }}
                    </button>
                    <span
                        role="status"
                        class="copy-status"
                        >{{ copyStatus }}</span
                    >
                </span>
            </template>
            <p
                v-if="isStale"
                class="stale"
            >
                {{
                    $gettext(
                        "This reflects the saved rule. Save your changes to update it.",
                    )
                }}
            </p>
        </div>
    </details>
</template>

<style scoped>
.index-sql {
    max-width: 90rem;
    font-size: 1.2rem;
    color: var(--abac-text-secondary);
}

.index-sql summary {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    border-radius: 0.4rem;
}

.index-sql summary:focus-visible {
    outline: 2px solid var(--abac-accent);
    outline-offset: 2px;
}

.index-sql-body {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    margin-top: 0.8rem;
}

.index-sql-body p {
    margin: 0;
}

.index-sql pre {
    margin: 0;
    padding: 1rem;
    overflow-x: auto;
    background: var(--abac-surface-bg);
    border: 1px solid var(--abac-border);
    border-radius: 0.6rem;
    color: var(--abac-text-primary);
    font-size: 1.15rem;
    white-space: pre;
}

.copy-row {
    display: inline-flex;
    align-items: center;
    gap: 0.8rem;
}

.copy-button {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.8rem;
    border: 1px solid var(--abac-border);
    border-radius: 0.4rem;
    background: var(--abac-surface-card);
    color: var(--abac-text-secondary);
    font: inherit;
    cursor: pointer;
}

.copy-button:hover {
    background: var(--abac-row-hover);
}

.copy-button:focus-visible {
    outline: 2px solid var(--abac-accent);
    outline-offset: 2px;
}

.stale {
    font-style: italic;
}
</style>
