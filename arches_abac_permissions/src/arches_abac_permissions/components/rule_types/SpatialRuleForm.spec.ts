import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SpatialRuleForm from "@/arches_abac_permissions/components/rule_types/SpatialRuleForm.vue";

import type { Polygon } from "geojson";
import type { SpatialDefinition } from "@/arches_abac_permissions/types";

const api = vi.hoisted(() => ({
    fetchMapConfig: vi.fn(),
    fetchResourceModelNodes: vi.fn(),
}));
vi.mock("@/arches_abac_permissions/api.ts", () => api);

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

function mountForm(definition: Partial<SpatialDefinition>) {
    const wrapper = mount(SpatialRuleForm, {
        props: {
            resourceModels: [{ graphid: "g", name: "Places" }],
            modelValue: definition,
            "onUpdate:modelValue": (value: Partial<SpatialDefinition>) =>
                wrapper.setProps({ modelValue: value }),
        },
        global: { stubs },
        attachTo: document.body,
    });
    return wrapper;
}

function lastDefinition(wrapper: ReturnType<typeof mountForm>) {
    return wrapper.props("modelValue") as Partial<SpatialDefinition>;
}

describe("SpatialRuleForm", () => {
    beforeEach(() => {
        api.fetchMapConfig.mockResolvedValue({
            basemap: null,
            bounds: null,
            min_zoom: 0,
            max_zoom: 20,
            sprite: "",
            glyphs: "",
        });
        api.fetchResourceModelNodes.mockResolvedValue([]);
    });

    it("loads geometry nodes and the map", async () => {
        const wrapper = mountForm({ graphid: "g" });
        await flushPromises();
        expect(api.fetchResourceModelNodes).toHaveBeenCalledWith(
            "g",
            "geojson-feature-collection",
        );
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

    it("shows an error when the map can't load", async () => {
        api.fetchMapConfig.mockRejectedValue(new Error("Map unavailable"));
        const wrapper = mountForm({});
        await flushPromises();
        expect(wrapper.findComponent(AreaMapStub).exists()).toBe(false);
        expect(wrapper.text()).toContain("Map unavailable");
        wrapper.unmount();
    });
});
