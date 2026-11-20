import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";

import GroupMembership from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupMembership/GroupMembership.vue";

import { ApiError } from "@/arches_abac_permissions/api.ts";

import type { User, UserDetails } from "@/arches_abac_permissions/types";

const mocks = vi.hoisted(() => ({
    fetchUsers: vi.fn(),
    fetchUserDetails: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    toastAdd: vi.fn(),
    confirmRequire: vi.fn(),
}));

vi.mock("@/arches_abac_permissions/api.ts", async (importOriginal) => ({
    ...(await importOriginal<
        typeof import("@/arches_abac_permissions/api.ts")
    >()),
    fetchUsers: mocks.fetchUsers,
    fetchUserDetails: mocks.fetchUserDetails,
    updateUser: mocks.updateUser,
    deleteUser: mocks.deleteUser,
    changeMembership: vi.fn(),
}));
vi.mock("openvue/usetoast", () => ({
    useToast: () => ({ add: mocks.toastAdd }),
}));
vi.mock("openvue/useconfirm", () => ({
    useConfirm: () => ({ require: mocks.confirmRequire }),
}));

const ButtonStub = defineComponent({
    props: { label: String, disabled: Boolean },
    setup(props) {
        return () => h("button", { disabled: props.disabled }, props.label);
    },
});
const DeleteUserDialogStub = defineComponent({
    props: { user: Object, details: Object },
    emits: ["delete", "deactivate", "close"],
    setup(props, { emit }) {
        return () =>
            props.user
                ? h("div", { class: "delete-stub" }, [
                      h("button", {
                          class: "stub-delete",
                          onClick: () => emit("delete", props.user),
                      }),
                      h("button", {
                          class: "stub-deactivate",
                          onClick: () => emit("deactivate", props.user),
                      }),
                  ])
                : null;
    },
});
const ToggleSwitchStub = defineComponent({
    props: { modelValue: Boolean, disabled: Boolean },
    emits: ["update:modelValue"],
    setup(props, { emit }) {
        return () =>
            h("button", {
                class: "stub-toggle",
                disabled: props.disabled,
                onClick: () => emit("update:modelValue", !props.modelValue),
            });
    },
});
const UserFormStub = defineComponent({
    props: { dirty: Boolean, user: Object },
    emits: ["created", "updated", "cancel", "update:dirty"],
    setup(_, { emit }) {
        return () =>
            h("div", { class: "new-user-form-stub" }, [
                h("button", {
                    class: "stub-updated",
                    onClick: () => emit("updated", editedDetails, false),
                }),
                h("button", {
                    class: "stub-dirty",
                    onClick: () => emit("update:dirty", true),
                }),
                h("button", {
                    class: "stub-created",
                    onClick: () => emit("created", newUser),
                }),
            ]);
    },
});

const existing: User = {
    id: 1,
    username: "alice",
    first_name: "Alice",
    last_name: "A",
    is_active: true,
    is_superuser: false,
    is_public: false,
    groups: [],
};
const newUser: User = {
    ...existing,
    id: 2,
    username: "bob",
    first_name: "Bob",
};

const editedDetails = {
    ...existing,
    first_name: "Alicia",
    email: "a@example.org",
} as UserDetails;

async function mountMembership() {
    const wrapper = mount(GroupMembership, {
        props: { groups: [] },
        global: {
            stubs: {
                Button: ButtonStub,
                UserForm: UserFormStub,
                DeleteUserDialog: DeleteUserDialogStub,
                ToggleSwitch: ToggleSwitchStub,
                InputText: true,
                Select: true,
                Checkbox: true,
                ProgressSpinner: true,
                GroupTags: true,
            },
        },
    });
    await flushPromises();
    return wrapper;
}

const addUserButton = (wrapper: Awaited<ReturnType<typeof mountMembership>>) =>
    wrapper.findAll("button").find((button) => button.text() === "Add User")!;

describe("GroupMembership add user", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.fetchUsers.mockResolvedValue({
            users: [existing],
            invite_expiry_hours: 72,
            current_user_id: 99,
        });
        mocks.fetchUserDetails.mockResolvedValue({
            ...existing,
            email: "",
            phone: "",
            can_delete: true,
        });
    });

    it("opens the new-user form from Add User and disables the button", async () => {
        const wrapper = await mountMembership();
        expect(wrapper.find(".new-user-form-stub").exists()).toBe(false);
        await addUserButton(wrapper).trigger("click");
        expect(wrapper.find(".new-user-form-stub").exists()).toBe(true);
        expect(addUserButton(wrapper).attributes("disabled")).toBeDefined();
    });

    it("selects the created user and shows a success toast", async () => {
        const wrapper = await mountMembership();
        await addUserButton(wrapper).trigger("click");
        await wrapper.get(".stub-created").trigger("click");
        await flushPromises();
        expect(wrapper.find(".new-user-form-stub").exists()).toBe(false);
        expect(mocks.fetchUserDetails).toHaveBeenCalledWith(newUser.id);
        expect(mocks.toastAdd).toHaveBeenCalledOnce();
    });

    it("confirms before discarding a dirty form", async () => {
        const wrapper = await mountMembership();
        await addUserButton(wrapper).trigger("click");
        await wrapper.get(".stub-dirty").trigger("click");
        await wrapper.get(".user-row button").trigger("click");
        expect(mocks.confirmRequire).toHaveBeenCalledOnce();
        expect(wrapper.find(".new-user-form-stub").exists()).toBe(true);
        mocks.confirmRequire.mock.calls[0][0].accept();
        await flushPromises();
        expect(wrapper.find(".new-user-form-stub").exists()).toBe(false);
    });

    const openUser = async (
        wrapper: Awaited<ReturnType<typeof mountMembership>>,
    ) => {
        await wrapper.get(".user-row .item-select").trigger("click");
        await flushPromises();
    };
    const findByText = (
        wrapper: Awaited<ReturnType<typeof mountMembership>>,
        text: string,
    ) =>
        wrapper
            .findAll("button")
            .find((button) => button.text().includes(text))!;

    it("opens the form in edit mode and applies the saved changes", async () => {
        const wrapper = await mountMembership();
        await openUser(wrapper);
        await findByText(wrapper, "Edit account").trigger("click");
        expect(wrapper.find(".new-user-form-stub").exists()).toBe(true);
        await wrapper.get(".stub-updated").trigger("click");
        await flushPromises();
        expect(wrapper.find(".new-user-form-stub").exists()).toBe(false);
        expect(wrapper.text()).toContain("Alicia A");
        expect(mocks.toastAdd).toHaveBeenCalledOnce();
    });

    it("deactivates and reactivates from the toggle", async () => {
        mocks.updateUser.mockResolvedValue({ ...existing, is_active: false });
        const wrapper = await mountMembership();
        await openUser(wrapper);
        await wrapper.get(".stub-toggle").trigger("click");
        await flushPromises();
        expect(mocks.updateUser).toHaveBeenCalledWith(1, { is_active: false });
        expect(wrapper.text()).toContain("Inactive");
    });

    it.each([
        ["yourself", { current_user_id: 1 }, {}],
        ["the public user", {}, { is_public: true }],
    ])("blocks the toggle for %s", async (_label, directory, overrides) => {
        mocks.fetchUsers.mockResolvedValue({
            users: [{ ...existing, ...overrides }],
            invite_expiry_hours: 72,
            current_user_id: 99,
            ...directory,
        });
        const wrapper = await mountMembership();
        await openUser(wrapper);
        expect(
            wrapper.get(".stub-toggle").attributes("disabled"),
        ).toBeDefined();
        expect(wrapper.find(".row-delete").exists()).toBe(false);
    });

    it("hides Edit account for the public user", async () => {
        mocks.fetchUsers.mockResolvedValue({
            users: [{ ...existing, is_public: true }],
            invite_expiry_hours: 72,
            current_user_id: 99,
        });
        const wrapper = await mountMembership();
        await openUser(wrapper);
        expect(findByText(wrapper, "Edit account")).toBeUndefined();
    });

    it("hides delete for superusers", async () => {
        mocks.fetchUsers.mockResolvedValue({
            users: [{ ...existing, is_superuser: true }],
            invite_expiry_hours: 72,
            current_user_id: 99,
        });
        const wrapper = await mountMembership();
        expect(wrapper.find(".row-delete").exists()).toBe(false);
    });

    it("deletes a user after loading its details", async () => {
        mocks.deleteUser.mockResolvedValue(undefined);
        const wrapper = await mountMembership();
        await wrapper.get(".row-delete").trigger("click");
        await flushPromises();
        expect(mocks.fetchUserDetails).toHaveBeenCalledWith(1);
        await wrapper.get(".stub-delete").trigger("click");
        await flushPromises();
        expect(mocks.deleteUser).toHaveBeenCalledWith(1);
        expect(wrapper.find(".user-row").exists()).toBe(false);
        expect(wrapper.find(".delete-stub").exists()).toBe(false);
        expect(mocks.toastAdd).toHaveBeenCalledOnce();
    });

    it("keeps the user when the server blocks the delete", async () => {
        mocks.deleteUser.mockRejectedValue(
            new ApiError("Has history", {}, "history"),
        );
        const wrapper = await mountMembership();
        await wrapper.get(".row-delete").trigger("click");
        await flushPromises();
        await wrapper.get(".stub-delete").trigger("click");
        await flushPromises();
        expect(wrapper.find(".user-row").exists()).toBe(true);
        expect(wrapper.find(".delete-stub").exists()).toBe(true);
        expect(mocks.toastAdd).not.toHaveBeenCalled();
    });

    it("deactivates from the delete dialog", async () => {
        mocks.updateUser.mockResolvedValue({ ...existing, is_active: false });
        const wrapper = await mountMembership();
        await wrapper.get(".row-delete").trigger("click");
        await flushPromises();
        await wrapper.get(".stub-deactivate").trigger("click");
        await flushPromises();
        expect(mocks.updateUser).toHaveBeenCalledWith(1, { is_active: false });
        expect(wrapper.find(".delete-stub").exists()).toBe(false);
        expect(wrapper.find(".user-row").exists()).toBe(true);
    });
});
