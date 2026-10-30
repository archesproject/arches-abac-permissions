import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import IndexSqlDisclosure from "@/arches_abac_permissions/components/IndexSqlDisclosure.vue";

const SQL = "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx ON tiles (x);";

describe("IndexSqlDisclosure", () => {
    it("asks to save an unsaved rule", () => {
        const wrapper = mount(IndexSqlDisclosure, {
            props: { isStale: false },
        });
        expect(wrapper.text()).toContain("Save the rule");
        expect(wrapper.find("pre").exists()).toBe(false);
    });

    it("explains when no index is needed", () => {
        const wrapper = mount(IndexSqlDisclosure, {
            props: { indexSql: null, isStale: false },
        });
        expect(wrapper.text()).toContain("doesn't need an additional index");
    });

    it("shows and copies the SQL", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        vi.stubGlobal("navigator", { clipboard: { writeText } });
        const wrapper = mount(IndexSqlDisclosure, {
            props: { indexSql: SQL, isStale: true },
        });
        expect(wrapper.find("pre").text()).toBe(SQL);
        expect(wrapper.find(".stale").exists()).toBe(true);
        await wrapper.find("button").trigger("click");
        await flushPromises();
        expect(writeText).toHaveBeenCalledWith(SQL);
        expect(wrapper.find("[role='status']").text()).toBe("Copied");
        vi.unstubAllGlobals();
    });
});
