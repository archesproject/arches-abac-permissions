import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";

import TileNodeValueRuleForm from "@/arches_abac_permissions/rule-types/tile-node-value/TileNodeValueRuleForm/TileNodeValueRuleForm.vue";

import type { VueWrapper } from "@vue/test-utils";
import type { TileNodeValueDefinition } from "@/arches_abac_permissions/rule-types/tile-node-value/types";

const api = vi.hoisted(() => ({
    fetchResourceModels: vi.fn(),
    fetchResourceModelNodes: vi.fn(),
    fetchLanguages: vi.fn(),
    fetchControlledListItems: vi.fn(),
}));
const toastAdd = vi.hoisted(() => vi.fn());

vi.mock(
    "@/arches_abac_permissions/rule-types/tile-node-value/api.ts",
    () => api,
);
vi.mock("openvue/usetoast", () => ({ useToast: () => ({ add: toastAdd }) }));

const SelectStub = defineComponent({
    props: {
        modelValue: { type: String, default: undefined },
        options: { type: Array, default: () => [] },
        inputId: { type: String, default: undefined },
    },
    emits: ["update:modelValue"],
    setup(props) {
        return () => h("div", { class: "select", id: props.inputId });
    },
});

const NODES = [
    {
        nodeid: "n-string",
        name: "Name",
        alias: "name",
        datatype: "string",
    },
    {
        nodeid: "n-bool",
        name: "Active",
        alias: "active",
        datatype: "boolean",
        true_label: "Yes",
        false_label: "No",
    },
];

function mountForm(definition: Partial<TileNodeValueDefinition>): VueWrapper {
    const wrapper = mount(TileNodeValueRuleForm, {
        props: {
            modelValue: definition,
            "onUpdate:modelValue": (value: Partial<TileNodeValueDefinition>) =>
                wrapper.setProps({ modelValue: value }),
        },
        global: {
            stubs: { Select: SelectStub, InputText: true },
        },
    });
    return wrapper;
}

function selectFor(wrapper: VueWrapper, inputId: string): VueWrapper {
    return wrapper
        .findAllComponents(SelectStub)
        .find((select) => select.props("inputId") === inputId)!;
}

describe("TileNodeValueRuleForm", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        api.fetchResourceModels.mockResolvedValue([
            { graphid: "g1", name: "Heritage Site" },
        ]);
        api.fetchResourceModelNodes.mockResolvedValue(NODES);
        api.fetchLanguages.mockResolvedValue([{ code: "en", name: "English" }]);
        api.fetchControlledListItems.mockResolvedValue([]);
    });

    it("loads models, and nodes for the selected model", async () => {
        const wrapper = mountForm({ graphid: "g1" });
        await flushPromises();
        expect(api.fetchResourceModels).toHaveBeenCalled();
        expect(api.fetchResourceModelNodes).toHaveBeenCalledWith("g1");
        expect(selectFor(wrapper, "abac-node").props("options")).toHaveLength(
            2,
        );
    });

    it("uses a text input and language picker for string nodes", async () => {
        const wrapper = mountForm({ graphid: "g1", nodeid: "n-string" });
        await flushPromises();
        expect(wrapper.find("#abac-node-value").exists()).toBe(true);
        expect(selectFor(wrapper, "abac-node-language").exists()).toBe(true);
        expect(api.fetchLanguages).toHaveBeenCalled();
        expect(wrapper.text()).toContain("Matches the full value exactly");
    });

    it("uses a select of labels for boolean nodes", async () => {
        const wrapper = mountForm({ graphid: "g1", nodeid: "n-bool" });
        await flushPromises();
        expect(selectFor(wrapper, "abac-node-value").props("options")).toEqual([
            { id: "true", label: "Yes" },
            { id: "false", label: "No" },
        ]);
        expect(api.fetchLanguages).not.toHaveBeenCalled();
    });

    it("clears the rest of the definition when the model changes", async () => {
        const wrapper = mountForm({
            graphid: "g1",
            nodeid: "n-string",
            value: "x",
        });
        await flushPromises();
        selectFor(wrapper, "abac-resource-model").vm.$emit(
            "update:modelValue",
            "g2",
        );
        await flushPromises();
        expect(wrapper.props("modelValue")).toEqual({ graphid: "g2" });
        expect(api.fetchResourceModelNodes).toHaveBeenLastCalledWith("g2");
    });

    it("shows a toast when nodes fail to load", async () => {
        api.fetchResourceModelNodes.mockRejectedValue(new Error("boom"));
        mountForm({ graphid: "g1" });
        await flushPromises();
        expect(toastAdd).toHaveBeenCalledWith(
            expect.objectContaining({
                severity: "error",
                summary: "Unable to load nodes",
                detail: "boom",
            }),
        );
    });
});
