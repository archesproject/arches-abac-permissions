import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ParentGroupsEditor from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupMembership/components/ParentGroupsEditor/ParentGroupsEditor.vue";

const MultiSelectStub = {
    props: ["modelValue", "options", "disabled"],
    emits: ["update:modelValue"],
    template: "<div class='multiselect' />",
};

function mountEditor(saving = false, inheritsFromIds: number[] = []) {
    return mount(ParentGroupsEditor, {
        props: {
            saving,
            inheritsFromIds,
            groupId: 1,
            groupName: "Inner",
            parentIds: [2],
            groups: [
                { id: 1, name: "Inner", parent_ids: [2] },
                { id: 2, name: "Outer", parent_ids: [] },
                { id: 3, name: "Other", parent_ids: [] },
                { id: 4, name: "Innermost", parent_ids: [1] },
            ],
        },
        global: { stubs: { MultiSelect: MultiSelectStub } },
    });
}

describe("ParentGroupsEditor", () => {
    it("offers every group except the one being edited and those inside it", () => {
        const select = mountEditor().findComponent(MultiSelectStub);
        expect(
            select.props("options").map((g: { id: number }) => g.id),
        ).toEqual([2, 3]);
        expect(select.props("modelValue")).toEqual([2]);
    });

    it("emits the new parent groups", async () => {
        const wrapper = mountEditor();
        await wrapper
            .findComponent(MultiSelectStub)
            .vm.$emit("update:modelValue", [3]);
        expect(wrapper.emitted("update-parents")).toEqual([[[3]]]);
    });

    it("is disabled while a save is in progress", () => {
        const select = mountEditor(true).findComponent(MultiSelectStub);
        expect(select.props("disabled")).toBe(true);
    });

    it("shows the saved parents again after a refused save", async () => {
        const wrapper = mountEditor();
        const select = () => wrapper.findComponent(MultiSelectStub);
        await select().vm.$emit("update:modelValue", [2, 3]);
        expect(select().props("modelValue")).toEqual([2, 3]);
        await wrapper.setProps({ saving: true });
        await wrapper.setProps({ saving: false });
        expect(select().props("modelValue")).toEqual([2]);
    });

    it("lists the groups whose rules members also get", () => {
        const inheritsFrom = mountEditor(false, [2, 3]).find(".inherits-from");
        expect(inheritsFrom.find(".inherits-from-label").text()).toBe(
            "Members also get the rules of:",
        );
        expect(inheritsFrom.text()).toContain("Outer, Other");
        expect(
            mountEditor(false, [3, 2]).find(".inherits-from").text(),
        ).toContain("Other, Outer");
        expect(mountEditor().find(".inherits-from").exists()).toBe(false);
    });
});
