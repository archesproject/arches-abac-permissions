import {
    AsYouType,
    getCountries,
    getCountryCallingCode,
    isSupportedCountry,
    parsePhoneNumberFromString,
    validatePhoneNumberLength,
} from "libphonenumber-js/max";

import type { CountryCode, PhoneNumber } from "libphonenumber-js/max";

import type { User } from "@/arches_abac_permissions/types";

export type TextStatus = "empty" | "format" | "taken" | "ok";
export type PhoneStatus =
    | "empty"
    | "incomplete"
    | "invalid"
    | "landline"
    | "ok";

export interface PhoneCountryOption {
    code: CountryCode;
    name: string;
    dialCode: string;
    flag: string;
}

export const USERNAME_PATTERN = /^[a-z0-9._-]{3,30}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const FALLBACK_COUNTRY: CountryCode = "US";
const REGIONAL_INDICATOR_OFFSET = 0x1f1e6 - "A".charCodeAt(0);

export function emailStatus(email: string): TextStatus {
    const trimmed = email.trim();
    if (!trimmed) {
        return "empty";
    }
    return EMAIL_PATTERN.test(trimmed) ? "ok" : "format";
}

export function usernameStatus(username: string, users: User[]): TextStatus {
    const name = username.trim().toLowerCase();
    if (!name) {
        return "empty";
    }
    if (!USERNAME_PATTERN.test(name)) {
        return "format";
    }
    return users.some((user) => user.username.toLowerCase() === name)
        ? "taken"
        : "ok";
}

export function defaultPhoneCountry(): CountryCode {
    try {
        const region = new Intl.Locale(navigator.language).maximize().region;
        if (region && isSupportedCountry(region)) {
            return region as CountryCode;
        }
    } catch {
        // Unparseable locale: use the fallback.
    }
    return FALLBACK_COUNTRY;
}

export function phoneCountryOptions(): PhoneCountryOption[] {
    const regionNames = new Intl.DisplayNames([navigator.language, "en"], {
        type: "region",
    });
    return getCountries()
        .map((code) => ({
            code,
            name: regionNames.of(code) ?? code,
            dialCode: `+${getCountryCallingCode(code)}`,
            flag: String.fromCodePoint(
                ...[...code].map(
                    (letter) =>
                        letter.charCodeAt(0) + REGIONAL_INDICATOR_OFFSET,
                ),
            ),
        }))
        .sort((first, second) => first.name.localeCompare(second.name));
}

export function parsePhone(
    phone: string,
    country: CountryCode,
): PhoneNumber | undefined {
    return parsePhoneNumberFromString(phone, country);
}

export function phoneStatus(phone: string, country: CountryCode): PhoneStatus {
    if (!phone.trim()) {
        return "empty";
    }
    const number = parsePhone(phone, country);
    if (!number?.isValid()) {
        return validatePhoneNumberLength(phone, country) === "TOO_SHORT"
            ? "incomplete"
            : "invalid";
    }
    return number.getType() === "FIXED_LINE" ? "landline" : "ok";
}

/** E.164 for a usable number, otherwise an empty string. */
export function toE164(phone: string, country: CountryCode): string {
    return parsePhone(phone, country)?.number ?? "";
}

/**
 * Formats as-you-type input. A full international number switches the
 * country; deletions and mid-number edits are left alone to keep the caret put.
 */
export function formatPhoneInput(
    raw: string,
    country: CountryCode,
    isTypingAtEnd: boolean,
): { phone: string; country: CountryCode } {
    if (raw.trim().startsWith("+")) {
        const number = parsePhone(raw, country);
        if (number?.isValid() && number.country) {
            return {
                phone: number.formatNational(),
                country: number.country,
            };
        }
        return { phone: new AsYouType().input(raw), country };
    }
    return {
        phone: isTypingAtEnd ? new AsYouType(country).input(raw) : raw,
        country,
    };
}

export function reformatPhone(phone: string, country: CountryCode): string {
    return phone
        ? new AsYouType(country).input(phone.replace(/[^\d]/g, ""))
        : phone;
}
