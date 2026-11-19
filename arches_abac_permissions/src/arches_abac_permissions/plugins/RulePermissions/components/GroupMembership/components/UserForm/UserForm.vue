<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useGettext } from "vue3-gettext";

import Button from "openvue/button";
import InputText from "openvue/inputtext";
import Message from "openvue/message";
import RadioButton from "openvue/radiobutton";
import Select from "openvue/select";

import {
    ApiError,
    createUser,
    updateUser,
} from "@/arches_abac_permissions/api.ts";
import { userDisplayName } from "@/arches_abac_permissions/utils.ts";
import {
    defaultPhoneCountry,
    emailStatus,
    formatPhoneInput,
    parsePhone,
    phoneCountryOptions,
    phoneStatus,
    reformatPhone,
    toE164,
    usernameStatus,
} from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupMembership/components/UserForm/user-form-utils.ts";

import type { CountryCode } from "libphonenumber-js/max";

import type { TextStatus } from "@/arches_abac_permissions/plugins/RulePermissions/components/GroupMembership/components/UserForm/user-form-utils.ts";

import type {
    NewUserFieldErrors,
    NewUserPayload,
    PasswordAction,
    User,
    UserDetails,
} from "@/arches_abac_permissions/types";

const PAYLOAD_FIELDS: (keyof NewUserPayload)[] = [
    "first_name",
    "last_name",
    "email",
    "username",
    "phone",
];
const MAX_NAME_LENGTH = 150;
const MAX_USERNAME_LENGTH = 30;
const PASSWORD_ACTIONS: PasswordAction[] = ["keep", "reset"];

const props = defineProps<{
    users: User[];
    inviteExpiryHours: number;
    user?: UserDetails;
}>();
const emit = defineEmits<{
    (e: "created", user: User): void;
    (e: "updated", user: UserDetails, resetSent: boolean): void;
    (e: "cancel"): void;
}>();
const isDirty = defineModel<boolean>("dirty", { default: false });

const { $gettext } = useGettext();

const countryOptions = phoneCountryOptions();
const countriesByCode = new Map(
    countryOptions.map((option) => [option.code, option]),
);

const isEditing = computed(() => props.user !== undefined);

function initialForm(): Record<keyof NewUserPayload, string> & {
    phoneCountry: CountryCode;
} {
    const phoneCountry = defaultPhoneCountry();
    const existing = props.user;
    if (!existing) {
        return {
            first_name: "",
            last_name: "",
            email: "",
            username: "",
            phone: "",
            phoneCountry,
        };
    }
    const number = parsePhone(existing.phone, phoneCountry);
    return {
        first_name: existing.first_name,
        last_name: existing.last_name,
        email: existing.email,
        username: existing.username,
        phone: number?.isValid() ? number.formatNational() : existing.phone,
        phoneCountry: number?.country ?? phoneCountry,
    };
}

const initial = initialForm();
const form = reactive({ ...initial });
const passwordAction = ref<PasswordAction>("keep");
const serverErrors = ref<NewUserFieldErrors>({});
const generalError = ref("");
const isSaving = ref(false);

const emailState = computed(() => emailStatus(form.email));
// Unchanged legacy usernames/phones are kept verbatim and not re-validated.
const isUsernameUnchanged = computed(
    () => isEditing.value && form.username.trim() === props.user?.username,
);
const isPhoneUnchanged = computed(
    () =>
        isEditing.value &&
        form.phone === initial.phone &&
        form.phoneCountry === initial.phoneCountry,
);
const usernameState = computed<TextStatus>(() =>
    isUsernameUnchanged.value
        ? "ok"
        : usernameStatus(
              form.username,
              props.users.filter((user) => user.id !== props.user?.id),
          ),
);
const phoneState = computed(() => phoneStatus(form.phone, form.phoneCountry));
const phoneNumber = computed(() => parsePhone(form.phone, form.phoneCountry));
const phoneCountryName = computed(
    () => countriesByCode.get(form.phoneCountry)?.name ?? form.phoneCountry,
);
const hasChanges = computed(
    () =>
        passwordAction.value === "reset" ||
        (isEditing.value
            ? PAYLOAD_FIELDS.some((field) => form[field] !== initial[field])
            : PAYLOAD_FIELDS.some((field) => form[field].trim() !== "")),
);
const isValid = computed(
    () =>
        Boolean(form.first_name.trim() && form.last_name.trim()) &&
        emailState.value === "ok" &&
        usernameState.value === "ok" &&
        (isPhoneUnchanged.value ||
            ["empty", "ok"].includes(phoneState.value)) &&
        Object.keys(serverErrors.value).length === 0,
);
const canSubmit = computed(() => isValid.value && hasChanges.value);
const usernameHint = computed(() =>
    $gettext("3–30 characters: letters, numbers, . _ -"),
);
const submitLabel = computed(() => {
    if (!isEditing.value) {
        return $gettext("Create & Send Invite");
    }
    return passwordAction.value === "reset"
        ? $gettext("Save & Send Reset Link")
        : $gettext("Save Changes");
});
const title = computed(() =>
    props.user
        ? $gettext("Edit Account: %{name}", {
              name: userDisplayName(props.user),
          })
        : $gettext("New Account"),
);
const inviteRecipient = computed(
    () => form.email.trim() || $gettext("the email address above"),
);

watch(
    () => PAYLOAD_FIELDS.map((field) => form[field]),
    (values, previous) => {
        PAYLOAD_FIELDS.forEach((field, index) => {
            if (values[index] !== previous[index]) {
                delete serverErrors.value[field];
            }
        });
    },
);
watch(hasChanges, (changed) => (isDirty.value = changed));

function onPhoneInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    const isDeleting = (event as InputEvent).inputType?.startsWith("delete");
    const formatted = formatPhoneInput(
        input.value,
        form.phoneCountry,
        input.selectionStart === input.value.length && !isDeleting,
    );
    form.phone = formatted.phone;
    form.phoneCountry = formatted.country;
    input.value = formatted.phone;
}

function onPhoneBlur(): void {
    if (phoneNumber.value?.isValid()) {
        form.phone = phoneNumber.value.formatNational();
    }
}

function onCountryChange(country: CountryCode): void {
    form.phoneCountry = country;
    form.phone = reformatPhone(form.phone, country);
}

async function submit(): Promise<void> {
    if (!canSubmit.value || isSaving.value) {
        return;
    }
    isSaving.value = true;
    generalError.value = "";
    const payload: NewUserPayload = {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        username: isUsernameUnchanged.value
            ? form.username.trim()
            : form.username.trim().toLowerCase(),
        phone: isPhoneUnchanged.value
            ? props.user?.phone ?? ""
            : toE164(form.phone, form.phoneCountry),
    };
    try {
        if (props.user) {
            const resetSent = passwordAction.value === "reset";
            const updated = await updateUser(props.user.id, {
                ...payload,
                password_action: passwordAction.value,
            });
            isDirty.value = false;
            emit("updated", updated, resetSent);
        } else {
            const created = await createUser(payload);
            isDirty.value = false;
            emit("created", created);
        }
    } catch (error) {
        if (
            error instanceof ApiError &&
            Object.keys(error.fieldErrors).length
        ) {
            serverErrors.value = error.fieldErrors;
        } else {
            generalError.value =
                error instanceof Error ? error.message : String(error);
        }
    } finally {
        isSaving.value = false;
    }
}
</script>

<template>
    <form
        class="new-user-form"
        novalidate
        @submit.prevent="submit"
    >
        <header class="new-user-header">
            <i
                class="pi"
                :class="isEditing ? 'pi-user-edit' : 'pi-user-plus'"
                aria-hidden="true"
            ></i>
            <h2 class="new-user-title">{{ title }}</h2>
            <span class="new-user-badge">{{
                isEditing ? $gettext("Editing") : $gettext("Draft")
            }}</span>
        </header>

        <div class="new-user-body">
            <fieldset class="new-user-section">
                <legend class="section-label">{{ $gettext("Person") }}</legend>
                <div class="new-user-row">
                    <div class="new-user-field">
                        <label for="new-user-first-name"
                            >{{ $gettext("First name")
                            }}<span class="required">*</span></label
                        >
                        <InputText
                            id="new-user-first-name"
                            v-model="form.first_name"
                            autocomplete="off"
                            :maxlength="MAX_NAME_LENGTH"
                        />
                    </div>
                    <div class="new-user-field">
                        <label for="new-user-last-name"
                            >{{ $gettext("Last name")
                            }}<span class="required">*</span></label
                        >
                        <InputText
                            id="new-user-last-name"
                            v-model="form.last_name"
                            autocomplete="off"
                            :maxlength="MAX_NAME_LENGTH"
                        />
                    </div>
                </div>
                <div class="new-user-field">
                    <label for="new-user-email"
                        >{{ $gettext("Email")
                        }}<span class="required">*</span></label
                    >
                    <InputText
                        id="new-user-email"
                        v-model="form.email"
                        type="email"
                        autocomplete="off"
                        spellcheck="false"
                        placeholder="name@example.org"
                        :invalid="
                            emailState === 'format' ||
                            Boolean(serverErrors.email)
                        "
                    />
                    <span
                        v-if="serverErrors.email"
                        class="hint err"
                        role="alert"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{ serverErrors.email }}</span
                    >
                    <span
                        v-else-if="emailState === 'format'"
                        class="hint err"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{ $gettext("Enter a valid email address") }}</span
                    >
                </div>
            </fieldset>

            <fieldset class="new-user-section">
                <legend class="section-label">{{ $gettext("Sign-in") }}</legend>
                <div class="new-user-field">
                    <label for="new-user-username"
                        >{{ $gettext("Username")
                        }}<span class="required">*</span></label
                    >
                    <div class="affix">
                        <span
                            class="affix-prefix"
                            aria-hidden="true"
                            >@</span
                        >
                        <InputText
                            id="new-user-username"
                            v-model="form.username"
                            class="username-input"
                            autocomplete="off"
                            spellcheck="false"
                            :maxlength="MAX_USERNAME_LENGTH"
                            :invalid="
                                usernameState === 'format' ||
                                usernameState === 'taken' ||
                                Boolean(serverErrors.username)
                            "
                        />
                    </div>
                    <span
                        v-if="serverErrors.username"
                        class="hint err"
                        role="alert"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{ serverErrors.username }}</span
                    >
                    <span
                        v-else-if="usernameState === 'ok'"
                        class="hint ok"
                        ><i
                            class="pi pi-check-circle"
                            aria-hidden="true"
                        ></i>
                        {{ $gettext("Username is available") }}</span
                    >
                    <span
                        v-else-if="usernameState === 'taken'"
                        class="hint err"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{ $gettext("That username is already in use") }}</span
                    >
                    <span
                        v-else-if="usernameState === 'format'"
                        class="hint err"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{ usernameHint }}</span
                    >
                    <span
                        v-else
                        class="hint"
                        >{{ usernameHint }}</span
                    >
                </div>
                <div
                    v-if="isEditing"
                    class="password-options"
                    role="radiogroup"
                    :aria-label="$gettext('Password')"
                >
                    <label
                        v-for="action in PASSWORD_ACTIONS"
                        :key="action"
                        class="password-option"
                        :for="`user-password-${action}`"
                    >
                        <RadioButton
                            v-model="passwordAction"
                            name="user-password-action"
                            :input-id="`user-password-${action}`"
                            :value="action"
                        />
                        {{
                            action === "keep"
                                ? $gettext("Keep current password")
                                : $gettext("Email a reset link")
                        }}
                    </label>
                </div>
                <div
                    v-if="isEditing && passwordAction === 'reset'"
                    class="new-user-note"
                >
                    <i
                        class="pi pi-send"
                        aria-hidden="true"
                    ></i>
                    <span>{{
                        $gettext(
                            "The person follows the link and chooses a new password. The link expires in %{hours} hours. Their current password keeps working until then.",
                            { hours: String(inviteExpiryHours) },
                        )
                    }}</span>
                </div>
                <div
                    v-else-if="!isEditing"
                    class="new-user-note"
                >
                    <i
                        class="pi pi-send"
                        aria-hidden="true"
                    ></i>
                    <span>{{
                        $gettext(
                            "An invitation link will be emailed to %{email}. The link expires in %{hours} hours.",
                            {
                                email: inviteRecipient,
                                hours: String(inviteExpiryHours),
                            },
                        )
                    }}</span>
                </div>
            </fieldset>

            <fieldset class="new-user-section">
                <legend class="section-label">{{ $gettext("Contact") }}</legend>
                <div class="new-user-field">
                    <label for="new-user-phone">{{
                        $gettext("Mobile phone")
                    }}</label>
                    <div class="phone">
                        <Select
                            class="phone-country"
                            filter
                            option-label="name"
                            option-value="code"
                            :aria-label="$gettext('Country')"
                            :model-value="form.phoneCountry"
                            :options="countryOptions"
                            :filter-fields="['name', 'dialCode', 'code']"
                            @update:model-value="onCountryChange"
                        >
                            <template #value="{ value }">
                                <span class="country-value"
                                    >{{ countriesByCode.get(value)?.flag }}
                                    {{
                                        countriesByCode.get(value)?.dialCode
                                    }}</span
                                >
                            </template>
                            <template #option="{ option }">
                                <span class="country-option">
                                    <span>{{ option.flag }}</span>
                                    <span class="country-name">{{
                                        option.name
                                    }}</span>
                                    <span class="country-dial">{{
                                        option.dialCode
                                    }}</span>
                                </span>
                            </template>
                        </Select>
                        <InputText
                            id="new-user-phone"
                            type="tel"
                            inputmode="tel"
                            autocomplete="off"
                            :model-value="form.phone"
                            :placeholder="$gettext('Mobile number')"
                            :invalid="
                                ['invalid', 'landline'].includes(phoneState) ||
                                Boolean(serverErrors.phone)
                            "
                            @input="onPhoneInput"
                            @blur="onPhoneBlur"
                        />
                    </div>
                    <span
                        v-if="serverErrors.phone"
                        class="hint err"
                        role="alert"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{ serverErrors.phone }}</span
                    >
                    <span
                        v-else-if="phoneState === 'ok' && phoneNumber"
                        class="hint ok"
                        ><i
                            class="pi pi-check-circle"
                            aria-hidden="true"
                        ></i>
                        {{
                            $gettext("%{kind} · %{number}", {
                                kind:
                                    phoneNumber.getType() === "MOBILE"
                                        ? $gettext("Mobile number")
                                        : $gettext("Valid number"),
                                number: phoneNumber.formatInternational(),
                            })
                        }}</span
                    >
                    <span
                        v-else-if="phoneState === 'landline'"
                        class="hint err"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{
                            $gettext(
                                "This is a landline. Enter a mobile number.",
                            )
                        }}</span
                    >
                    <span
                        v-else-if="phoneState === 'invalid'"
                        class="hint err"
                        ><i
                            class="pi pi-times-circle"
                            aria-hidden="true"
                        ></i>
                        {{
                            $gettext("Not a valid %{country} number", {
                                country: phoneCountryName,
                            })
                        }}</span
                    >
                    <span
                        v-else-if="phoneState === 'incomplete'"
                        class="hint"
                        >{{
                            $gettext("Too short for a %{country} number", {
                                country: phoneCountryName,
                            })
                        }}</span
                    >
                    <span
                        v-else
                        class="hint"
                        >{{
                            $gettext(
                                "Optional. Type or paste the number. Starting with + picks the country automatically.",
                            )
                        }}</span
                    >
                </div>
            </fieldset>

            <p class="required-note">
                <span class="required">*</span>
                {{
                    isEditing
                        ? $gettext("Required.")
                        : $gettext(
                              "Required. Group membership can be assigned once the account is created.",
                          )
                }}
            </p>
            <Message
                v-if="generalError"
                severity="error"
                role="alert"
            >
                {{ generalError }}
            </Message>
        </div>

        <footer class="new-user-footer">
            <Button
                type="button"
                severity="secondary"
                :label="$gettext('Cancel')"
                @click="emit('cancel')"
            />
            <Button
                type="submit"
                icon="pi pi-send"
                :label="submitLabel"
                :disabled="!canSubmit"
                :loading="isSaving"
            />
        </footer>
    </form>
</template>

<style scoped>
.new-user-form {
    grid-row: 1 / -1;
    display: flex;
    flex-direction: column;
    min-block-size: 0;
}

.new-user-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding-block: 1.4rem;
    padding-inline: 2rem 1.4rem;
    border-block-end: 0.1rem solid
        color-mix(in srgb, var(--p-abac-accent) 30%, var(--p-abac-border));
    background: color-mix(
        in srgb,
        var(--p-abac-accent) 10%,
        var(--p-abac-surface-bg)
    );
}

.new-user-header .pi {
    font-size: 1.6rem;
    color: var(--p-abac-accent);
}

.new-user-title {
    margin: 0;
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--p-abac-text-primary);
}

.new-user-badge {
    flex-shrink: 0;
    padding: 0.2rem 0.7rem;
    border-radius: 1rem;
    background: var(--p-abac-accent);
    color: var(--p-abac-surface-card);
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.new-user-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2.4rem;
    min-block-size: 0;
    max-inline-size: 56rem;
    padding-block: 2rem;
    padding-inline: 2rem 1.4rem;
    overflow-y: auto;
}

.new-user-section {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
    min-inline-size: 0;
    margin: 0;
    padding: 0;
    border: none;
}

.section-label {
    margin-block-end: 1rem;
    padding: 0;
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--p-abac-text-secondary);
}

.new-user-row {
    display: flex;
    gap: 1.2rem;
}

.new-user-row > .new-user-field {
    flex: 1;
}

.new-user-field {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    min-inline-size: 0;
}

.new-user-field label {
    font-size: 1.1rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--p-abac-text-secondary);
}

.required {
    margin-inline-start: 0.2rem;
    color: var(--p-abac-danger);
}

.affix {
    position: relative;
    display: flex;
    align-items: center;
}

.affix-prefix {
    position: absolute;
    inset-inline-start: 1rem;
    font-size: 1.35rem;
    font-weight: 600;
    color: var(--p-abac-text-secondary);
    pointer-events: none;
}

.affix .username-input {
    inline-size: 100%;
    padding-inline-start: 2.6rem;
    font-family: monospace;
}

.hint {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}

.hint .pi {
    font-size: 1rem;
}

.hint.ok {
    color: var(--p-abac-status-active-text);
}

.hint.err {
    color: var(--p-abac-danger);
}

.phone {
    display: flex;
    gap: 0.8rem;
}

.phone > :last-child {
    flex: 1;
    min-inline-size: 0;
}

.phone-country {
    flex-shrink: 0;
    inline-size: 11rem;
}

.country-option {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    inline-size: 100%;
}

.country-name {
    flex: 1;
    min-inline-size: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.country-dial {
    color: var(--p-abac-text-secondary);
    font-variant-numeric: tabular-nums;
}

.password-options {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
}

.password-option {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    font-size: 1.3rem;
    cursor: pointer;
}

.new-user-note {
    display: flex;
    align-items: flex-start;
    gap: 0.8rem;
    padding: 0.9rem 1.1rem;
    border: 0.1rem solid
        color-mix(in srgb, var(--p-abac-accent) 30%, transparent);
    border-radius: 0.6rem;
    background: var(--p-abac-accent-tint);
    font-size: 1.2rem;
    line-height: 1.5;
    color: var(--p-abac-text-primary);
}

.new-user-note .pi {
    flex-shrink: 0;
    margin-block-start: 0.2rem;
    font-size: 1.3rem;
    color: var(--p-abac-accent);
}

.required-note {
    margin: 0;
    padding-block-start: 1.2rem;
    border-block-start: 0.1rem solid var(--p-abac-border);
    font-size: 1.15rem;
    color: var(--p-abac-text-secondary);
}

.required-note .required {
    margin-inline-start: 0;
}

.new-user-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.8rem;
    padding-block: 1rem;
    padding-inline: 2rem 1.4rem;
    border-block-start: 0.1rem solid var(--p-abac-border);
    background: var(--p-abac-surface-bg);
}
</style>
