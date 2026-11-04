import type { Component } from "vue";

import type { RuleDefinition } from "@/arches_abac_permissions/types";

// Front-end half of a rule type; the key matches the server's RuleType.key.
export interface RuleTypeModule<D = RuleDefinition> {
    key: string;
    // Edits the definition via v-model and loads any options it needs.
    form: Component;
    isComplete(definition: Partial<D>): boolean;
}
