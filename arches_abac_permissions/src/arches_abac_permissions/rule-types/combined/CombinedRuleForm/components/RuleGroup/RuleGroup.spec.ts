import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";

import RuleGroup from "@/arches_abac_permissions/rule-types/combined/CombinedRuleForm/components/RuleGroup/RuleGroup.vue";
import { toGroup } from "@/arches_abac_permissions/rule-types/combined/group.ts";

import type { CombinedGroup } from "@/arches_abac_permissions/rule-types/combined/types";

const ButtonStub = defineComponent({
    props: { label: { type: String, default: "" } },
    emits: ["click"],
    setup(props, { emit }) {
        return () =>
            h(
                "button",
                { type: "button", onClick: () => emit("click") },
                props.label,
            );
    },
});

function mountGroup(group: CombinedGroup) {
    return mount(RuleGroup, {
        props: {
            modelValue: group,
            inputId: "test",
            ruleOptions: [{ id: "a", label: "Rule A" }],
            isLoading: false,
            isNested: false,
        },
        global: {
            stubs: { Button: ButtonStub, Select: true, MultiSelect: true },
        },
    });
}

function lastUpdate(wrapper: ReturnType<typeof mountGroup>): CombinedGroup {
    const updates = wrapper.emitted("update:modelValue") ?? [];
    return updates.at(-1)?.[0] as CombinedGroup;
}

describe("RuleGroup", () => {
    it("adds an empty group", async () => {
        const wrapper = mountGroup(toGroup({ rule_ids: ["a"] }));
        await wrapper.find("button").trigger("click");
        expect(lastUpdate(wrapper).groups).toEqual([toGroup({})]);
        expect(lastUpdate(wrapper).rule_ids).toEqual(["a"]);
    });

    it("removes the group that asks to be removed", async () => {
        const first = toGroup({ operator: "and", rule_ids: ["a"] });
        const second = toGroup({ operator: "or", rule_ids: ["a"] });
        const wrapper = mountGroup(toGroup({ groups: [first, second] }));
        const children = wrapper.findAllComponents(RuleGroup);
        children.at(0)?.vm.$emit("remove");
        expect(lastUpdate(wrapper).groups).toEqual([second]);
    });

    it("passes a nested group's changes up", async () => {
        const child = toGroup({ rule_ids: ["a"] });
        const wrapper = mountGroup(toGroup({ groups: [child] }));
        const changed = { ...child, operator: "and" as const };
        wrapper
            .findAllComponents(RuleGroup)
            .at(0)
            ?.vm.$emit("update:modelValue", changed);
        expect(lastUpdate(wrapper).groups).toEqual([changed]);
    });
});
