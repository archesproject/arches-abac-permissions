import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";

import AreaMap from "@/arches_abac_permissions/rule-types/spatial/SpatialRuleForm/components/AreaMap/AreaMap.vue";

import type { Point, Polygon } from "geojson";

vi.mock("vue3-gettext", () => ({
    useGettext: () => ({
        $gettext: (text: string, values: Record<string, string> = {}) =>
            text.replace(/%\{(\w+)\}/g, (_, key) => values[key]),
        $ngettext: (
            one: string,
            many: string,
            count: number,
            values: Record<string, string> = {},
        ) =>
            (count === 1 ? one : many).replace(
                /%\{(\w+)\}/g,
                (_, key) => values[key],
            ),
    }),
}));

const context = vi.hoisted(() => ({
    map: { value: {} },
    drawnFeatures: { value: [] as unknown[] },
    setBufferForFeature: vi.fn(),
    deleteAllDrawnFeatures: vi.fn(),
    addFeatures: vi.fn(),
}));

vi.mock("@/arches_vue_components/components", () => ({
    useDefaultMapInteractionTools: () =>
        ["tools", "basemap", "overlays", "legend", "settings"].map((name) => ({
            name,
        })),
    MapComponent: {
        name: "MapComponent",
        props: ["value", "interactionTools"],
        emits: ["update:value"],
        setup(_: unknown, { expose }: { expose: (api: unknown) => void }) {
            expose({ context });
            return {};
        },
        template: "<div class='map-stub' />",
    },
}));

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
const point: Point = { type: "Point", coordinates: [2, 3] };

function feature(
    geometry: unknown,
    bufferDistance = 0,
    id = "a",
    units = "meters",
) {
    return {
        type: "Feature",
        id,
        geometry,
        properties: { buffer_distance: bufferDistance, buffer_units: units },
    };
}

function mountMap(props: Record<string, unknown> = {}) {
    const area = ref<unknown>(props.modelValue);
    const wrapper = mount(AreaMap, {
        props: {
            modelValue: area.value,
            "onUpdate:modelValue": (value: unknown) => {
                area.value = value;
                void wrapper.setProps({ modelValue: value });
            },
            ...props,
        } as never,
    });
    return { wrapper, area };
}

describe("AreaMap", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        context.drawnFeatures.value = [];
    });

    it("passes the initial area to the map as a feature collection", () => {
        const { wrapper } = mountMap({ modelValue: square, buffer: 5 });
        const value = wrapper
            .findComponent({ name: "MapComponent" })
            .props("value") as {
            features: { geometry: unknown; properties: unknown }[];
        };
        expect(value.features).toHaveLength(1);
        expect(value.features[0].geometry).toEqual(square);
        expect(value.features[0].properties).toMatchObject({
            buffer_distance: 5,
            buffer_units: "meters",
        });
        expect(wrapper.find("[role=status]").text()).toBe(
            "The area has 1 polygon.",
        );
    });

    it("offers only map tools, basemaps and overlays", () => {
        const { wrapper } = mountMap();
        const tools = wrapper
            .findComponent({ name: "MapComponent" })
            .props("interactionTools") as { name: string }[];
        expect(tools.map((tool) => tool.name)).toEqual([
            "tools",
            "basemap",
            "overlays",
        ]);
    });

    it("reports drawn features as an area", async () => {
        const { wrapper, area } = mountMap();
        expect(wrapper.find("[role=status]").text()).toBe(
            "No area has been drawn.",
        );
        await wrapper
            .findComponent({ name: "MapComponent" })
            .vm.$emit("update:value", {
                type: "FeatureCollection",
                features: [feature(square), feature(point)],
            });
        await nextTick();
        expect(area.value).toEqual({
            type: "GeometryCollection",
            geometries: [square, point],
        });
        expect(wrapper.find("[role=status]").text()).toBe(
            "The area has 1 polygon, 1 point.",
        );
    });

    it("applies the buffer to drawn features that differ", async () => {
        const stale = feature(point, 0);
        const current = feature(square, 20);
        context.drawnFeatures.value = [stale, current];
        const { wrapper } = mountMap({ modelValue: point, buffer: 20 });
        await wrapper.setProps({ buffer: 50 });
        expect(context.setBufferForFeature).toHaveBeenCalledWith(
            stale,
            50,
            "meters",
        );
        expect(context.setBufferForFeature).toHaveBeenCalledWith(
            current,
            50,
            "meters",
        );
    });

    it("pushes external area changes onto the map", async () => {
        const { wrapper } = mountMap({ modelValue: square });
        await wrapper.setProps({ modelValue: point });
        expect(context.deleteAllDrawnFeatures).toHaveBeenCalled();
        expect(context.addFeatures).toHaveBeenCalledTimes(1);
        const added = context.addFeatures.mock.calls[0][0];
        expect(added[0].geometry).toEqual(point);
    });

    it("doesn't echo the map's own changes back to it", async () => {
        const { wrapper } = mountMap();
        await wrapper
            .findComponent({ name: "MapComponent" })
            .vm.$emit("update:value", {
                type: "FeatureCollection",
                features: [feature(square)],
            });
        await nextTick();
        expect(context.deleteAllDrawnFeatures).not.toHaveBeenCalled();
    });

    it("links the map to its help text", () => {
        const { wrapper } = mountMap({ describedBy: "help" });
        expect(wrapper.find(".map-frame").attributes()).toMatchObject({
            role: "group",
            "aria-describedby": "help",
        });
    });

    it("adopts a buffer edited in the map tools for every shape", async () => {
        const { wrapper } = mountMap({ modelValue: square });
        const map = wrapper.findComponent({ name: "MapComponent" });
        const other = feature(point, 0, "b");
        const edited = feature(square, 2, "a", "kilometers");
        context.drawnFeatures.value = [edited, other];
        await map.vm.$emit("update:value", {
            type: "FeatureCollection",
            features: [feature(square, 0, "a")],
        });
        expect(wrapper.emitted("update:buffer")).toBeUndefined();
        await map.vm.$emit("update:value", {
            type: "FeatureCollection",
            features: [edited, other],
        });
        expect(wrapper.emitted("update:buffer")).toEqual([[2000]]);
        expect(context.setBufferForFeature).toHaveBeenCalledWith(
            edited,
            2000,
            "meters",
        );
        expect(context.setBufferForFeature).toHaveBeenCalledWith(
            other,
            2000,
            "meters",
        );
    });

    it("gives newly drawn shapes the current buffer", async () => {
        const { wrapper } = mountMap({ modelValue: square, buffer: 30 });
        const fresh = feature(point, 0, "new");
        context.drawnFeatures.value = [fresh];
        await wrapper
            .findComponent({ name: "MapComponent" })
            .vm.$emit("update:value", {
                type: "FeatureCollection",
                features: [fresh],
            });
        expect(wrapper.emitted("update:buffer")).toBeUndefined();
        expect(context.setBufferForFeature).toHaveBeenCalledWith(
            fresh,
            30,
            "meters",
        );
    });
});
