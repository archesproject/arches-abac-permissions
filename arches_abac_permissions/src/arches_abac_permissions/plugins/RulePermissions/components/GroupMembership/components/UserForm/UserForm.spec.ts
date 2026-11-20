import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";

import UserForm from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupMembership/components/UserForm/UserForm.vue";
import { ApiError } from "@/arches_abac_permissions/api.ts";

import type { User, UserDetails } from "@/arches_abac_permissions/types";

const mocks = vi.hoisted(() => ({
    createUser: vi.fn(),
    updateUser: vi.fn(),
}));
const mockCreateUser = mocks.createUser;

vi.mock("@/arches_abac_permissions/api.ts", async (importOriginal) => ({
    ...(await importOriginal<
        typeof import("@/arches_abac_permissions/api.ts")
    >()),
    createUser: mocks.createUser,
    updateUser: mocks.updateUser,
}));

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

const RadioStub = defineComponent({
    props: { modelValue: String, value: String, inputId: String },
    emits: ["update:modelValue"],
    setup(props, { emit }) {
        return () =>
            h("input", {
                id: props.inputId,
                type: "radio",
                checked: props.modelValue === props.value,
                onChange: () => emit("update:modelValue", props.value),
            });
    },
});

const existingUser = {
    id: 1,
    username: "Taken.Name",
    first_name: "A",
    last_name: "B",
} as User;
const createdUser = { ...existingUser, id: 2, username: "new.person" };

const editedUser = {
    id: 1,
    username: "Taken.Name",
    first_name: "Ann",
    last_name: "Bell",
    email: "ann@example.org",
    phone: "+16502530000",
} as UserDetails;

function mountForm(user?: UserDetails) {
    return mount(UserForm, {
        props: { users: [existingUser], inviteExpiryHours: 72, user },
        global: {
            stubs: {
                RadioButton: RadioStub,
                InputText: InputTextStub,
                Button: ButtonStub,
                Select: true,
                Message: { template: "<div role='alert'><slot /></div>" },
            },
        },
    });
}

async function fill(
    wrapper: ReturnType<typeof mountForm>,
    id: string,
    value: string,
) {
    await wrapper.get(`#${id}`).setValue(value);
}

async function fillValid(wrapper: ReturnType<typeof mountForm>) {
    await fill(wrapper, "new-user-first-name", " Ada ");
    await fill(wrapper, "new-user-last-name", "Lovelace");
    await fill(wrapper, "new-user-email", "ada@example.org");
    await fill(wrapper, "new-user-username", "Ada.L");
}

const submitButton = (wrapper: ReturnType<typeof mountForm>) =>
    wrapper.get("button[type=submit]");

describe("UserForm", () => {
    beforeEach(() => {
        mockCreateUser.mockReset();
    });

    it("disables submit until required fields are valid", async () => {
        const wrapper = mountForm();
        expect(submitButton(wrapper).attributes("disabled")).toBeDefined();
        await fillValid(wrapper);
        expect(submitButton(wrapper).attributes("disabled")).toBeUndefined();
    });

    it("flags a malformed email and username", async () => {
        const wrapper = mountForm();
        await fill(wrapper, "new-user-email", "nope");
        await fill(wrapper, "new-user-username", "a!");
        expect(wrapper.text()).toContain("Enter a valid email address");
        expect(wrapper.find(".hint.err").exists()).toBe(true);
        expect(submitButton(wrapper).attributes("disabled")).toBeDefined();
    });

    it("reports availability case-insensitively", async () => {
        const wrapper = mountForm();
        await fill(wrapper, "new-user-username", "taken.name");
        expect(wrapper.text()).toContain("That username is already in use");
        await fill(wrapper, "new-user-username", "fresh.name");
        expect(wrapper.text()).toContain("Username is available");
    });

    it.each([
        ["+1 650 253 0000", "%{kind}", true],
        ["+44 20 7946 0958", "landline", false],
        ["+1 123", "Too short", false],
        ["+1 000 000 0000", "Not a valid", false],
    ])("phone %s shows %s", async (phone, hint, canSubmit) => {
        const wrapper = mountForm();
        await fillValid(wrapper);
        await fill(wrapper, "new-user-phone", phone);
        expect(wrapper.text()).toContain(hint);
        expect(submitButton(wrapper).attributes("disabled") === undefined).toBe(
            canSubmit,
        );
    });

    it("submits a normalized payload with an E.164 phone", async () => {
        mockCreateUser.mockResolvedValue(createdUser);
        const wrapper = mountForm();
        await fillValid(wrapper);
        await fill(wrapper, "new-user-phone", "+1 650 253 0000");
        await wrapper.get("form").trigger("submit");
        await flushPromises();
        expect(mockCreateUser).toHaveBeenCalledWith({
            first_name: "Ada",
            last_name: "Lovelace",
            email: "ada@example.org",
            username: "ada.l",
            phone: "+16502530000",
        });
        expect(wrapper.emitted("created")?.[0]).toEqual([createdUser]);
    });

    it("sends an empty phone when none is entered", async () => {
        mockCreateUser.mockResolvedValue(createdUser);
        const wrapper = mountForm();
        await fillValid(wrapper);
        await wrapper.get("form").trigger("submit");
        await flushPromises();
        expect(mockCreateUser.mock.calls[0][0].phone).toBe("");
    });

    it("shows server field errors inline and clears them on edit", async () => {
        mockCreateUser.mockRejectedValue(
            new ApiError("Invalid", { email: "Email already in use" }),
        );
        const wrapper = mountForm();
        await fillValid(wrapper);
        await wrapper.get("form").trigger("submit");
        await flushPromises();
        expect(wrapper.text()).toContain("Email already in use");
        expect(wrapper.emitted("created")).toBeUndefined();
        await fill(wrapper, "new-user-email", "other@example.org");
        expect(wrapper.text()).not.toContain("Email already in use");
    });

    it("shows other errors in a message", async () => {
        mockCreateUser.mockRejectedValue(new ApiError("Email failed"));
        const wrapper = mountForm();
        await fillValid(wrapper);
        await wrapper.get("form").trigger("submit");
        await flushPromises();
        expect(wrapper.get("[role=alert]").text()).toBe("Email failed");
    });

    it("describes the invitation link", async () => {
        const wrapper = mountForm();
        await fill(wrapper, "new-user-email", "ada@example.org");
        expect(wrapper.text()).toContain("An invitation link will be emailed");
    });

    it("tracks dirtiness and emits cancel", async () => {
        const wrapper = mountForm();
        await fill(wrapper, "new-user-first-name", "Ada");
        expect(wrapper.emitted("update:dirty")?.at(-1)).toEqual([true]);
        await wrapper.get("button[type=button]").trigger("click");
        expect(wrapper.emitted("cancel")).toHaveLength(1);
    });

    describe("edit mode", () => {
        beforeEach(() => mocks.updateUser.mockReset());

        it("prefills the account and shows edit wording", () => {
            const wrapper = mountForm(editedUser);
            expect(wrapper.text()).toContain("Edit Account: %{name}");
            expect(wrapper.text()).toContain("Editing");
            expect(wrapper.text()).not.toContain("Draft");
            expect(
                wrapper.get<HTMLInputElement>("#new-user-email").element.value,
            ).toBe("ann@example.org");
            expect(wrapper.get("#new-user-phone").element.value).toContain(
                "650",
            );
            expect(wrapper.text()).toContain("Keep current password");
            expect(wrapper.text()).not.toContain("invitation link");
        });

        it("needs a valid change before saving and ignores its own username", async () => {
            const wrapper = mountForm(editedUser);
            expect(wrapper.text()).not.toContain("already in use");
            expect(submitButton(wrapper).text()).toBe("Save Changes");
            expect(submitButton(wrapper).attributes("disabled")).toBeDefined();
            await fill(wrapper, "new-user-first-name", "Anna");
            expect(
                submitButton(wrapper).attributes("disabled"),
            ).toBeUndefined();
            await fill(wrapper, "new-user-email", "nope");
            expect(submitButton(wrapper).attributes("disabled")).toBeDefined();
            expect(wrapper.emitted("update:dirty")?.at(-1)).toEqual([true]);
        });

        it("keeps an unchanged legacy username and phone verbatim", async () => {
            mocks.updateUser.mockResolvedValue(editedUser);
            const wrapper = mountForm({
                ...editedUser,
                username: "Jane@X.org",
                phone: "555-1234",
            });
            expect(wrapper.text()).not.toContain("Enter a valid");
            await fill(wrapper, "new-user-first-name", "Anna");
            expect(
                submitButton(wrapper).attributes("disabled"),
            ).toBeUndefined();
            await wrapper.get("form").trigger("submit");
            await flushPromises();
            const payload = mocks.updateUser.mock.calls[0][1];
            expect(payload.username).toBe("Jane@X.org");
            expect(payload.phone).toBe("555-1234");
            await fill(wrapper, "new-user-username", "Jane@X.org!");
            expect(submitButton(wrapper).attributes("disabled")).toBeDefined();
        });

        it("saves changes with the keep action", async () => {
            mocks.updateUser.mockResolvedValue(editedUser);
            const wrapper = mountForm(editedUser);
            await fill(wrapper, "new-user-first-name", "Anna");
            await wrapper.get("form").trigger("submit");
            await flushPromises();
            expect(mocks.updateUser).toHaveBeenCalledWith(1, {
                first_name: "Anna",
                last_name: "Bell",
                email: "ann@example.org",
                username: "Taken.Name",
                phone: "+16502530000",
                password_action: "keep",
            });
            expect(wrapper.emitted("updated")?.[0]).toEqual([
                editedUser,
                false,
            ]);
        });

        it("offers a reset link without other changes", async () => {
            mocks.updateUser.mockResolvedValue(editedUser);
            const wrapper = mountForm(editedUser);
            await wrapper.get("#user-password-reset").setValue(true);
            expect(wrapper.text()).toContain(
                "Their current password keeps working",
            );
            expect(submitButton(wrapper).text()).toBe("Save & Send Reset Link");
            await wrapper.get("form").trigger("submit");
            await flushPromises();
            expect(mocks.updateUser.mock.calls[0][1].password_action).toBe(
                "reset",
            );
            expect(wrapper.emitted("updated")?.[0]).toEqual([editedUser, true]);
        });
    });
});
