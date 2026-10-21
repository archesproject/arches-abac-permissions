import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";

import GroupPermissions from "@/arches_abac_permissions/components/GroupPermissions.vue";
import { newDraft } from "@/arches_abac_permissions/utils.ts";

const CheckboxStub = defineComponent({
    props: { modelValue: Boolean, ariaLabel: String },
    emits: ["update:modelValue"],
    setup(props, { emit }) {
        return () =>
            h("input", {
                type: "checkbox",
                checked: props.modelValue,
                "aria-label": props.ariaLabel,
                onChange: (event: Event) =>
                    emit(
                        "update:modelValue",
                        (event.target as HTMLInputElement).checked,
                    ),
            });
    },
});

const groups = [
    { id: 1, name: "Editors", member_count: 0 },
    { id: 2, name: "Viewers", member_count: 0 },
];

function mountComponent() {
    const draft = newDraft("lifecycle_state");
    const wrapper = mount(GroupPermissions, {
        props: {
            modelValue: draft,
            groups,
            canSave: true,
            isDirty: true,
            isSaving: false,
        },
        global: {
            stubs: {
                Checkbox: CheckboxStub,
                Button: { template: "<button type='button'><slot /></button>" },
                ToggleSwitch: true,
            },
        },
    });
    return { wrapper, draft };
}

describe("GroupPermissions", () => {
    it("toggles a single permission", async () => {
        const { wrapper, draft } = mountComponent();
        const box = wrapper.find(
            "input[aria-label='%{ permission } for %{ group }']",
        );
        await box.setValue(true);
        expect(draft.grants[1]).toEqual(["read"]);
    });

    it("grants and revokes a permission for all groups", async () => {
        const { wrapper, draft } = mountComponent();
        const grantAll = wrapper.findAll("button.link-button")[0];
        await grantAll.trigger("click");
        expect(draft.grants).toEqual({ 1: ["read"], 2: ["read"] });
        await wrapper.findAll("button.link-button")[1].trigger("click");
        expect(draft.grants).toEqual({ 1: [], 2: [] });
    });

    it("selects all and clears one group", async () => {
        const { wrapper, draft } = mountComponent();
        const rowButtons = wrapper
            .findAll("tbody tr")[0]
            .findAll("button.link-button");
        await rowButtons[0].trigger("click");
        expect(draft.grants[1]).toEqual(["read", "update", "delete"]);
        await rowButtons[1].trigger("click");
        expect(draft.grants[1]).toEqual([]);
    });
});
