import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";

import DeleteUserDialog from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupMembership/components/DeleteUserDialog/DeleteUserDialog.vue";

import type { User, UserDetails } from "@/arches_abac_permissions/types";

const DialogStub = defineComponent({
    props: { visible: Boolean, header: String },
    setup(_, { slots }) {
        return () => h("div", slots.default?.());
    },
});
const InputTextStub = defineComponent({
    props: { modelValue: String },
    emits: ["update:modelValue"],
    setup(props, { emit }) {
        return () =>
            h("input", {
                value: props.modelValue,
                onInput: (event: Event) =>
                    emit(
                        "update:modelValue",
                        (event.target as HTMLInputElement).value,
                    ),
            });
    },
});
const ButtonStub = defineComponent({
    props: { label: String, disabled: Boolean, type: String },
    setup(props) {
        return () =>
            h(
                "button",
                { type: props.type, disabled: props.disabled },
                props.label,
            );
    },
});

const user = {
    id: 5,
    username: "carol",
    first_name: "Carol",
    last_name: "C",
    is_active: true,
} as User;
const deletable = { ...user, can_delete: true } as UserDetails;
const blocked = {
    ...user,
    can_delete: false,
    delete_block_code: "history",
    delete_block_reason: "Has published graphs. Deactivate it instead.",
} as UserDetails;

function mountDialog(details: UserDetails | null, target: User = user) {
    return mount(DeleteUserDialog, {
        props: {
            user: target,
            details,
            groupNames: ["Editors", "Reviewers"],
            isDeleting: false,
        },
        global: {
            stubs: {
                Dialog: DialogStub,
                InputText: InputTextStub,
                Button: ButtonStub,
                Message: { template: "<div role='alert'><slot /></div>" },
            },
        },
    });
}

const deleteButton = (wrapper: ReturnType<typeof mountDialog>) =>
    wrapper.get("button[type=submit]");

describe("DeleteUserDialog", () => {
    it("lists group memberships", () => {
        expect(mountDialog(deletable).text()).toContain(
            "Removal from %{count} group(s)",
        );
    });

    it("requires the exact username before deleting", async () => {
        const wrapper = mountDialog(deletable);
        expect(deleteButton(wrapper).attributes("disabled")).toBeDefined();
        await wrapper.get("input").setValue("carl");
        expect(deleteButton(wrapper).attributes("disabled")).toBeDefined();
        await wrapper.get("input").setValue("carol");
        expect(deleteButton(wrapper).attributes("disabled")).toBeUndefined();
        await wrapper.get("form").trigger("submit");
        expect(wrapper.emitted("delete")?.[0]).toEqual([user]);
    });

    it("stays disabled while details load", () => {
        const wrapper = mountDialog(null);
        expect(wrapper.get("input").attributes("disabled")).toBeDefined();
        expect(deleteButton(wrapper).attributes("disabled")).toBeDefined();
    });

    it("explains a blocked delete and offers deactivation", async () => {
        const wrapper = mountDialog(blocked);
        expect(wrapper.get("[role=alert]").text()).toContain("Deactivate it");
        expect(wrapper.get("input").attributes("disabled")).toBeDefined();
        expect(deleteButton(wrapper).attributes("disabled")).toBeDefined();
        const deactivate = wrapper
            .findAll("button")
            .find((button) => button.text() === "Deactivate")!;
        await deactivate.trigger("click");
        expect(wrapper.emitted("deactivate")?.[0]).toEqual([user]);
    });

    it("hides deactivation for an inactive user", () => {
        const wrapper = mountDialog(deletable, { ...user, is_active: false });
        expect(wrapper.text()).not.toContain("Deactivate");
    });
});
