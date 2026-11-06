import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import PrimeVue from "openvue/config";
import InputNumber from "openvue/inputnumber";

describe("buffer InputNumber", () => {
    it("puts aria-describedby on the input element", () => {
        const wrapper = mount(InputNumber, {
            props: {
                inputId: "abac-buffer",
                pt: {
                    pcInputText: { root: { "aria-describedby": "help-id" } },
                },
            },
            global: { plugins: [PrimeVue] },
        });
        expect(wrapper.find("input").attributes("aria-describedby")).toBe(
            "help-id",
        );
        expect(wrapper.element.getAttribute("aria-describedby")).toBeNull();
    });
});
