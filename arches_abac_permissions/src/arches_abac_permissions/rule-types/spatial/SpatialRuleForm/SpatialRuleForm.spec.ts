import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SpatialRuleForm from "@/arches_abac_permissions/rule-types/spatial/SpatialRuleForm/SpatialRuleForm.vue";

import type { Polygon } from "geojson";
import type { VueWrapper } from "@vue/test-utils";
import type { SpatialDefinition } from "@/arches_abac_permissions/rule-types/spatial/types";

const api = vi.hoisted(() => ({
    fetchMapConfig: vi.fn(),
    fetchGeometryNodes: vi.fn(),
    fetchResourceModels: vi.fn(),
}));
const toastAdd = vi.hoisted(() => vi.fn());

vi.mock("@/arches_abac_permissions/rule-types/spatial/api.ts", () => api);
vi.mock("openvue/usetoast", () => ({ useToast: () => ({ add: toastAdd }) }));

const AreaMapStub = {
    name: "AreaMap",
    props: ["modelValue", "config", "describedBy"],
    template: "<div class='area-map-stub' />",
};

const stubs = {
    AreaMap: AreaMapStub,
    Button: {
        props: ["label"],
        template: "<button type='button'>{{ label }}</button>",
    },
    Message: { template: "<div role='alert'><slot /></div>" },
    ProgressSpinner: true,
    Select: true,
    Textarea: {
        props: ["modelValue"],
        emits: ["update:modelValue"],
        template:
            "<textarea :value='modelValue' @input=\"$emit('update:modelValue', $event.target.value)\" />",
    },
};

const square: Polygon = {
    type: "Polygon",
    coordinates: [
        [
            [0, 0],
            [1, 0],
            [1, 1],
            [0, 0],
        ],
    ],
};

function mountForm(definition: Partial<SpatialDefinition>): VueWrapper {
    const wrapper = mount(SpatialRuleForm, {
        props: {
            modelValue: definition,
            "onUpdate:modelValue": (value: Partial<SpatialDefinition>) =>
                wrapper.setProps({ modelValue: value }),
        },
        global: { stubs },
        attachTo: document.body,
    });
    return wrapper;
}

function lastDefinition(wrapper: VueWrapper): Partial<SpatialDefinition> {
    return wrapper.props("modelValue") as Partial<SpatialDefinition>;
}

describe("SpatialRuleForm", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        api.fetchResourceModels.mockResolvedValue([
            { graphid: "g", name: "Places" },
        ]);
        api.fetchMapConfig.mockResolvedValue({
            basemaps: [],
            bounds: null,
            min_zoom: 0,
            max_zoom: 20,
            sprite: "",
            glyphs: "",
        });
        api.fetchGeometryNodes.mockResolvedValue([]);
    });

    it("loads models, geometry nodes and the map", async () => {
        const wrapper = mountForm({ graphid: "g" });
        await flushPromises();
        expect(api.fetchResourceModels).toHaveBeenCalled();
        expect(api.fetchGeometryNodes).toHaveBeenCalledWith("g");
        const map = wrapper.findComponent(AreaMapStub);
        expect(map.exists()).toBe(true);
        expect(map.props("describedBy")).toBe("abac-area-help");
        wrapper.unmount();
    });

    it("keeps the area when the drawn map changes", async () => {
        const wrapper = mountForm({ graphid: "g", nodeid: "n" });
        await flushPromises();
        wrapper
            .findComponent(AreaMapStub)
            .vm.$emit("update:modelValue", square);
        await flushPromises();
        expect(lastDefinition(wrapper)).toEqual({
            graphid: "g",
            nodeid: "n",
            geometry: square,
        });
        wrapper.unmount();
    });

    it("applies valid GeoJSON and reports invalid GeoJSON", async () => {
        const wrapper = mountForm({ graphid: "g", nodeid: "n" });
        await flushPromises();
        const textarea = wrapper.find("#abac-area-geojson");
        const apply = wrapper
            .findAll("button")
            .find((button) => button.text().includes("Apply GeoJSON"))!;

        await textarea.setValue('{"type": "Point", "coordinates": [0, 0]}');
        await apply.trigger("click");
        expect(wrapper.find("[role='alert']").exists()).toBe(true);
        expect(textarea.attributes("aria-describedby")).toBe(
            "abac-area-geojson-error",
        );
        expect(lastDefinition(wrapper).geometry).toBeUndefined();

        await textarea.setValue(JSON.stringify(square));
        await apply.trigger("click");
        expect(wrapper.find("[role='alert']").exists()).toBe(false);
        expect(lastDefinition(wrapper).geometry).toEqual(square);
        wrapper.unmount();
    });

    it("keeps the area but drops the node when the model changes", async () => {
        const wrapper = mountForm({
            graphid: "g",
            nodeid: "n",
            geometry: square,
        });
        await flushPromises();
        wrapper
            .findAllComponents({ name: "Select" })
            .find(
                (select) =>
                    select.attributes("input-id") === "abac-resource-model",
            )
            ?.vm.$emit("update:modelValue", "other");
        await flushPromises();
        expect(lastDefinition(wrapper)).toEqual({
            graphid: "other",
            geometry: square,
        });
        wrapper.unmount();
    });

    it("shows an error when the map can't load", async () => {
        api.fetchMapConfig.mockRejectedValue(new Error("Map unavailable"));
        const wrapper = mountForm({});
        await flushPromises();
        expect(wrapper.findComponent(AreaMapStub).exists()).toBe(false);
        expect(wrapper.text()).toContain("Map unavailable");
        wrapper.unmount();
    });
});
