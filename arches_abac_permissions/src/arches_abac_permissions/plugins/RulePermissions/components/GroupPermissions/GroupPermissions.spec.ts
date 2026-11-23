import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";

import GroupPermissions from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupPermissions/GroupPermissions.vue";
import { newDraft } from "@/arches_abac_permissions/utils.ts";

vi.mock("vue3-gettext", () => ({
    useGettext: () => ({
        $gettext: (text: string, values: Record<string, string> = {}) => {
            let translated = text;
            for (const [key, value] of Object.entries(values)) {
                translated = translated.replaceAll(`%{${key}}`, value);
            }
            return translated;
        },
    }),
}));

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

function mountComponent(groupList: object[] = groups) {
    const draft = newDraft("lifecycle_state");
    const wrapper = mount(GroupPermissions, {
        props: {
            modelValue: draft,
            groups: groupList,
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
        const box = wrapper.find("input[aria-label='Read for Editors']");
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

    it("shows grants a group gets through nesting", async () => {
        const { wrapper, draft } = mountComponent([
            { id: 1, name: "Inner", member_count: 0, inherits_from_ids: [2] },
            { id: 2, name: "Outer", member_count: 0, inherits_from_ids: [] },
        ]);
        await wrapper.setProps({
            modelValue: { ...draft, grants: { 2: ["read"] } },
        });
        const rows = wrapper.findAll("tbody tr");
        expect(rows[0].find(".inherited").text()).toBe(
            "Also gets Read via Outer",
        );
        expect(rows[1].find(".inherited").exists()).toBe(false);
    });

    it("warns when grants reach a public group through nesting", async () => {
        const { wrapper, draft } = mountComponent([
            { id: 1, name: "Staff", member_count: 0, inherits_from_ids: [] },
            {
                id: 2,
                name: "Guest",
                member_count: 0,
                is_public: true,
                inherits_from_ids: [1],
            },
        ]);
        expect(wrapper.find(".public-warning").exists()).toBe(false);
        await wrapper.setProps({
            modelValue: { ...draft, grants: { 1: ["read"] } },
        });
        expect(wrapper.find(".public-warning").exists()).toBe(true);
    });

    it("marks groups and permissions they get through nesting", async () => {
        const { wrapper, draft } = mountComponent([
            { id: 1, name: "Inner", member_count: 0, inherits_from_ids: [2] },
            { id: 2, name: "Outer", member_count: 0, inherits_from_ids: [] },
        ]);
        await wrapper.setProps({
            modelValue: {
                ...draft,
                grants: { 1: ["update"], 2: ["read", "update"] },
            },
        });
        const [inner, outer] = wrapper.findAll("tbody tr");
        expect(inner.classes()).toContain("inherits");
        expect(outer.classes()).not.toContain("inherits");
        // Read comes only through Outer; Update is also granted directly.
        expect(
            inner
                .findAll(".inherited-mark")
                .map((mark) => mark.attributes("aria-label")),
        ).toEqual(["Read inherited via Outer"]);
    });
});
