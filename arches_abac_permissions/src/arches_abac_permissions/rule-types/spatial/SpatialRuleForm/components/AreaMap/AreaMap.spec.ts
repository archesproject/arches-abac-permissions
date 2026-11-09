import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AreaMap from "@/arches_abac_permissions/rule-types/spatial/SpatialRuleForm/components/AreaMap/AreaMap.vue";

import type { MapConfig } from "@/arches_abac_permissions/rule-types/spatial/types";

const mapMock = vi.hoisted(() => ({
    setLayoutProperty: vi.fn(),
    handlers: {} as Record<string, () => void>,
}));

vi.mock("vue3-gettext", () => {
    const format = (text: string, values: Record<string, string> = {}) =>
        text.replace(/%\{(\w+)\}/g, (_match, key) => values[key]);
    return {
        useGettext: () => ({
            $gettext: format,
            $ngettext: (
                one: string,
                many: string,
                count: number,
                values?: Record<string, string>,
            ) => format(count === 1 ? one : many, values),
        }),
    };
});

vi.mock("maplibre-gl", () => ({
    Map: class {
        on(event: string, handler: () => void) {
            mapMock.handlers[event] = handler;
        }
        getCanvas() {
            return { setAttribute: vi.fn() };
        }
        addControl() {}
        addSource() {}
        addLayer() {}
        getLayer() {
            return {};
        }
        getSource() {
            return undefined;
        }
        setLayoutProperty(...args: unknown[]) {
            mapMock.setLayoutProperty(...args);
        }
        remove() {}
    },
    NavigationControl: class {},
    setWorkerUrl() {},
}));

vi.mock("@mapbox/mapbox-gl-draw", () => ({
    default: class {
        getAll() {
            return { type: "FeatureCollection", features: [] };
        }
        set() {}
        deleteAll() {}
        changeMode() {}
    },
}));

const OVERLAY_NAMES = ["Parcels", "Roads & Paths", "Rivers"];

function layer(name: string) {
    const id = name.toLowerCase();
    return {
        name,
        layers: [{ id, type: "fill", source: id }],
        sources: { [id]: { type: "geojson", data: {} } },
    };
}

const config: MapConfig = {
    basemaps: [layer("streets")],
    overlays: OVERLAY_NAMES.map(layer),
    default_basemap: "streets",
    bounds: null,
    min_zoom: 0,
    max_zoom: 20,
    sprite: null,
    glyphs: null,
} as unknown as MapConfig;

const stubs = {
    Button: {
        props: ["label", "disabled"],
        template:
            "<button type='button' :disabled='disabled'>{{ label }}</button>",
    },
    Checkbox: {
        props: ["modelValue", "inputId"],
        emits: ["update:modelValue"],
        template:
            "<input type='checkbox' :id='inputId' :checked='modelValue' @change=\"$emit('update:modelValue', $event.target.checked)\" />",
    },
    Select: true,
};

function mountMap(overlayConfig: MapConfig = config) {
    return mount(AreaMap, {
        props: { config: overlayConfig, modelValue: undefined },
        global: { stubs },
    });
}

function button(wrapper: ReturnType<typeof mountMap>, label: string) {
    return wrapper.findAll("button").find((entry) => entry.text() === label)!;
}

describe("AreaMap overlays", () => {
    beforeEach(() => {
        mapMock.setLayoutProperty.mockClear();
    });

    it("renders a collapsed disclosure with a hidden legend", () => {
        const wrapper = mountMap();
        const details = wrapper.find("details.overlays");
        expect(details.exists()).toBe(true);
        expect(details.attributes("open")).toBeUndefined();
        expect(details.find("summary").text()).toBe("Overlays (0 of 3 shown)");
        expect(details.find("fieldset legend").text()).toBe("Overlays");
    });

    it("lists every overlay with index-based ids", () => {
        const wrapper = mountMap();
        const labels = wrapper.findAll(".overlay-list label");
        expect(labels.map((entry) => entry.text())).toEqual(OVERLAY_NAMES);
        expect(labels.map((entry) => entry.attributes("for"))).toEqual([
            "abac-overlay-0",
            "abac-overlay-1",
            "abac-overlay-2",
        ]);
        expect(wrapper.find("#abac-overlay-1").exists()).toBe(true);
    });

    it("updates the summary count when toggling", async () => {
        const wrapper = mountMap();
        await wrapper.find("#abac-overlay-0").setValue(true);
        expect(wrapper.find("summary").text()).toBe("Overlays (1 of 3 shown)");
        await wrapper.find("#abac-overlay-0").setValue(false);
        expect(wrapper.find("summary").text()).toBe("Overlays (0 of 3 shown)");
    });

    it("shows and hides all overlays and sets layer visibility", async () => {
        const wrapper = mountMap();
        mapMock.handlers.load();
        mapMock.setLayoutProperty.mockClear();
        expect(
            button(wrapper, "Hide all").attributes("disabled"),
        ).toBeDefined();
        expect(
            button(wrapper, "Show all").attributes("disabled"),
        ).toBeUndefined();

        await button(wrapper, "Show all").trigger("click");
        await flushPromises();
        expect(wrapper.find("summary").text()).toBe("Overlays (3 of 3 shown)");
        for (const name of OVERLAY_NAMES) {
            expect(mapMock.setLayoutProperty).toHaveBeenCalledWith(
                name.toLowerCase(),
                "visibility",
                "visible",
            );
        }
        expect(
            button(wrapper, "Show all").attributes("disabled"),
        ).toBeDefined();
        expect(
            button(wrapper, "Hide all").attributes("disabled"),
        ).toBeUndefined();

        await button(wrapper, "Hide all").trigger("click");
        await flushPromises();
        expect(wrapper.find("summary").text()).toBe("Overlays (0 of 3 shown)");
        expect(mapMock.setLayoutProperty).toHaveBeenCalledWith(
            "parcels",
            "visibility",
            "none",
        );
        expect(
            button(wrapper, "Hide all").attributes("disabled"),
        ).toBeDefined();
    });

    it("omits the disclosure when there are no overlays", () => {
        const wrapper = mountMap({ ...config, overlays: [] });
        expect(wrapper.find("details.overlays").exists()).toBe(false);
    });
});
