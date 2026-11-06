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
    props: ["modelValue", "config", "buffer", "describedBy"],
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
    InputNumber: {
        name: "InputNumber",
        props: ["modelValue", "pt"],
        emits: ["update:modelValue"],
        template: "<input type='number' :value='modelValue' />",
    },
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

function findSelect(wrapper: VueWrapper, inputId: string): VueWrapper {
    return wrapper
        .findAllComponents({ name: "Select" })
        .find((select) => select.attributes("input-id") === inputId)!;
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
            overlays: [],
            default_basemap: null,
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

        await textarea.setValue('{"type": "Circle", "coordinates": [0, 0]}');
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

    it("sets and clears the buffer and passes it to the map", async () => {
        const wrapper = mountForm({ graphid: "g", nodeid: "n" });
        await flushPromises();
        const input = wrapper.findComponent({ name: "InputNumber" });
        expect(input.props("pt")).toEqual({
            pcInputText: { root: { "aria-describedby": "abac-buffer-help" } },
        });
        expect(wrapper.find("#abac-buffer-help").text()).toContain(
            "greater than 0",
        );
        input.vm.$emit("update:modelValue", 250);
        await flushPromises();
        expect(lastDefinition(wrapper).buffer).toBe(250);
        expect(wrapper.findComponent(AreaMapStub).props("buffer")).toBe(250);
        input.vm.$emit("update:modelValue", 0);
        await flushPromises();
        expect("buffer" in lastDefinition(wrapper)).toBe(false);
        input.vm.$emit("update:modelValue", 5);
        await flushPromises();
        input.vm.$emit("update:modelValue", null);
        await flushPromises();
        expect("buffer" in lastDefinition(wrapper)).toBe(false);
        wrapper.unmount();
    });

    it("shows the area as a FeatureCollection and copies it", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.assign(navigator, { clipboard: { writeText } });
        const wrapper = mountForm({
            graphid: "g",
            nodeid: "n",
            geometry: square,
        });
        await flushPromises();
        wrapper.find("details").element.setAttribute("open", "");
        await wrapper.find("details").trigger("toggle");
        const text = (
            wrapper.find("#abac-area-geojson").element as HTMLTextAreaElement
        ).value;
        expect(JSON.parse(text)).toEqual({
            type: "FeatureCollection",
            features: [{ type: "Feature", properties: {}, geometry: square }],
        });

        const copy = wrapper
            .findAll("button")
            .find((button) => button.text().includes("Copy GeoJSON"))!;
        await copy.trigger("click");
        await flushPromises();
        expect(JSON.parse(writeText.mock.calls[0][0]).type).toBe(
            "FeatureCollection",
        );
        expect(toastAdd).toHaveBeenCalledWith(
            expect.objectContaining({ severity: "success" }),
        );

        writeText.mockRejectedValue(new Error("denied"));
        await copy.trigger("click");
        await flushPromises();
        expect(toastAdd).toHaveBeenLastCalledWith(
            expect.objectContaining({ severity: "error", detail: "denied" }),
        );
        wrapper.unmount();
    });

    it("disables copying when there is no area", async () => {
        const wrapper = mountForm({ graphid: "g", nodeid: "n" });
        await flushPromises();
        const copy = wrapper
            .findAll("button")
            .find((button) => button.text().includes("Copy GeoJSON"))!;
        expect(copy.attributes("disabled")).toBeDefined();
        wrapper.unmount();
    });

    it("applies point and line GeoJSON", async () => {
        const wrapper = mountForm({ graphid: "g", nodeid: "n" });
        await flushPromises();
        await wrapper
            .find("#abac-area-geojson")
            .setValue('{"type": "Point", "coordinates": [0, 0]}');
        await wrapper
            .findAll("button")
            .find((button) => button.text().includes("Apply GeoJSON"))!
            .trigger("click");
        expect(lastDefinition(wrapper).geometry).toEqual({
            type: "GeometryCollection",
            geometries: [{ type: "Point", coordinates: [0, 0] }],
        });
        wrapper.unmount();
    });

    it("keeps the area and operator but drops the node when the model changes", async () => {
        const wrapper = mountForm({
            graphid: "g",
            nodeid: "n",
            geometry: square,
            buffer: 10,
            operator: "within",
        });
        await flushPromises();
        findSelect(wrapper, "abac-resource-model").vm.$emit(
            "update:modelValue",
            "other",
        );
        await flushPromises();
        expect(lastDefinition(wrapper)).toEqual({
            graphid: "other",
            geometry: square,
            buffer: 10,
            operator: "within",
        });
        wrapper.unmount();
    });

    it("defaults to intersects and describes the chosen operator", async () => {
        const wrapper = mountForm({ graphid: "g", nodeid: "n" });
        await flushPromises();
        const operatorSelect = findSelect(wrapper, "abac-spatial-operator");
        expect(operatorSelect.attributes("model-value")).toBe("intersects");
        expect(wrapper.find("#abac-area-help").text()).toContain(
            "touches or overlaps",
        );

        operatorSelect.vm.$emit("update:modelValue", "centroid");
        await flushPromises();
        expect(lastDefinition(wrapper)).toEqual({
            graphid: "g",
            nodeid: "n",
            operator: "centroid",
        });
        expect(wrapper.find("#abac-area-help").text()).toContain("centre");
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
