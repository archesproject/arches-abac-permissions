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
            "input[aria-label='%{permission} for %{group}']",
        );
        await box.setValue(true);
        expect(draft.grants[1]).toEqual(["read"]);
    });

    it("toggles a permission for all groups", async () => {
        const { wrapper, draft } = mountComponent();
        const grantRead = () => wrapper.findAll("button.grant-button")[0];
        expect(grantRead().text()).toContain("Grant");
        await grantRead().trigger("click");
        expect(draft.grants).toEqual({ 1: ["read"], 2: ["read"] });
        expect(grantRead().text()).toContain("Revoke");
        await grantRead().trigger("click");
        expect(draft.grants).toEqual({ 1: [], 2: [] });
    });

    it("grants all to a partially granted permission", async () => {
        const { wrapper, draft } = mountComponent();
        draft.grants[1] = ["read"];
        await wrapper.vm.$nextTick();
        await wrapper.findAll("button.grant-button")[0].trigger("click");
        expect(draft.grants).toEqual({ 1: ["read"], 2: ["read"] });
    });

    it("toggles select all and clear for one group", async () => {
        const { wrapper, draft } = mountComponent();
        const rowToggle = () =>
            wrapper.findAll("tbody tr")[0].find("button.link-button");
        expect(rowToggle().text()).toBe("Select all");
        await rowToggle().trigger("click");
        expect(draft.grants[1]).toEqual(["read", "update", "delete"]);
        expect(rowToggle().text()).toBe("Clear selection");
        await rowToggle().trigger("click");
        expect(draft.grants[1]).toEqual([]);
    });
});
