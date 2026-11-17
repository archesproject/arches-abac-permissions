import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SearchRuleForm from "@/arches_abac_permissions/rule-types/search/SearchRuleForm/SearchRuleForm.vue";

import type { VueWrapper } from "@vue/test-utils";
import type {
    AdvancedSearchQuery,
    SavedSearch,
    SearchDefinition,
} from "@/arches_abac_permissions/rule-types/search/types";

const api = vi.hoisted(() => ({ fetchSavedSearches: vi.fn() }));
const toastAdd = vi.hoisted(() => vi.fn());

vi.mock("@/arches_abac_permissions/rule-types/search/api.ts", () => api);
vi.mock("openvue/usetoast", () => ({ useToast: () => ({ add: toastAdd }) }));

// The shared setup's $gettext returns the msgid as is; this one fills in %{...}.
vi.mock("vue3-gettext", () => ({
    useGettext: () => ({
        $gettext: (text: string, values: Record<string, string> = {}) =>
            text.replace(/%\{(\w+)\}/g, (_match, key: string) => values[key]),
    }),
}));

const SelectStub = {
    name: "Select",
    props: ["modelValue", "options", "loading"],
    emits: ["update:modelValue"],
    template: "<div class='select-stub' />",
};

const stubs = {
    Select: SelectStub,
    Textarea: {
        props: ["modelValue"],
        emits: ["update:modelValue"],
        template:
            "<textarea :value='modelValue' @input=\"$emit('update:modelValue', $event.target.value)\" />",
    },
};

const QUERY: AdvancedSearchQuery = {
    graph_slug: "monument",
    scope: "RESOURCE",
    logic: "AND",
    clauses: [{ type: "LITERAL" }],
    groups: [],
};

function savedSearch(
    id: string,
    name: string,
    username: string,
    advancedQuery: AdvancedSearchQuery | null,
): SavedSearch {
    return {
        savedsearchid: id,
        name,
        description: "",
        creator: { id: 1, username },
        query_definition: {
            terms: advancedQuery ? [] : [{ id: "free-text" }],
            queries: advancedQuery ? { advancedQuery } : {},
            graphSlugs: ["monument"],
            mapFilter: null,
        },
    };
}

const CASTLES = savedSearch("own-1", "Castles", "admin", QUERY);
const FREE_TEXT = savedSearch("own-2", "Free text", "admin", null);
const SHARED = savedSearch("shared-1", "Abbeys", "colleague", {
    ...QUERY,
    graph_slug: "abbey",
});

function mountForm(definition: Partial<SearchDefinition>): VueWrapper {
    const wrapper = mount(SearchRuleForm, {
        props: {
            modelValue: definition,
            "onUpdate:modelValue": (value: Partial<SearchDefinition>) =>
                wrapper.setProps({ modelValue: value }),
        },
        global: { stubs },
    });
    return wrapper;
}

function textarea(wrapper: VueWrapper): HTMLTextAreaElement {
    return wrapper.find("#abac-search-query").element as HTMLTextAreaElement;
}

function select(wrapper: VueWrapper): VueWrapper {
    return wrapper.findComponent(SelectStub);
}

function lastDefinition(wrapper: VueWrapper): Partial<SearchDefinition> {
    return wrapper.props("modelValue") as Partial<SearchDefinition>;
}

describe("SearchRuleForm", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        api.fetchSavedSearches.mockResolvedValue({
            mine: [CASTLES, FREE_TEXT],
            shared: [SHARED],
        });
    });

    it("lists own and shared saved searches, disabling unusable ones", async () => {
        const wrapper = mountForm({});
        await flushPromises();
        expect(select(wrapper).props("options")).toEqual([
            {
                label: "Your saved searches",
                items: [
                    { id: "own-1", label: "Castles", disabled: false },
                    {
                        id: "own-2",
                        label: "Free text: can't be used for a rule",
                        disabled: true,
                    },
                ],
            },
            {
                label: "Shared with you",
                items: [
                    {
                        id: "shared-1",
                        label: "Abbeys (by colleague)",
                        disabled: false,
                    },
                ],
            },
        ]);
    });

    it("fills the query from a chosen saved search", async () => {
        const wrapper = mountForm({});
        await flushPromises();
        select(wrapper).vm.$emit("update:modelValue", "shared-1");
        await flushPromises();
        expect(lastDefinition(wrapper)).toEqual({
            advanced_search_query:
                SHARED.query_definition.queries.advancedQuery,
        });
        expect(JSON.parse(textarea(wrapper).value).graph_slug).toBe("abbey");
        expect(select(wrapper).props("modelValue")).toBe("shared-1");
    });

    it("clears the chosen saved search when the query is edited", async () => {
        const wrapper = mountForm({});
        await flushPromises();
        select(wrapper).vm.$emit("update:modelValue", "own-1");
        await flushPromises();
        await wrapper.find("#abac-search-query").setValue("{}");
        expect(select(wrapper).props("modelValue")).toBeNull();
    });

    it("reports saved searches that fail to load", async () => {
        api.fetchSavedSearches.mockRejectedValue(new Error("offline"));
        mountForm({});
        await flushPromises();
        expect(toastAdd).toHaveBeenCalledWith(
            expect.objectContaining({
                summary: "Unable to load saved searches",
                detail: "offline",
            }),
        );
    });

    it("shows a saved query as formatted JSON", () => {
        const wrapper = mountForm({ advanced_search_query: QUERY });
        expect(JSON.parse(textarea(wrapper).value)).toEqual(QUERY);
        expect(wrapper.text()).toContain("Resource model: monument");
    });

    it("stores a pasted query", async () => {
        const wrapper = mountForm({});
        await wrapper
            .find("#abac-search-query")
            .setValue(JSON.stringify(QUERY));
        expect(lastDefinition(wrapper)).toEqual({
            advanced_search_query: QUERY,
        });
        expect(wrapper.find("[role='alert']").exists()).toBe(false);
    });

    it("reports invalid JSON and keeps the text", async () => {
        const wrapper = mountForm({ advanced_search_query: QUERY });
        await wrapper.find("#abac-search-query").setValue("{ not json");
        expect(lastDefinition(wrapper)).toEqual({});
        expect(wrapper.find("[role='alert']").text()).toContain(
            "Paste the query as JSON",
        );
        expect(textarea(wrapper).value).toBe("{ not json");
    });

    it("rejects JSON that is not an object", async () => {
        const wrapper = mountForm({});
        await wrapper.find("#abac-search-query").setValue("[1, 2]");
        expect(lastDefinition(wrapper)).toEqual({});
        expect(wrapper.find("[role='alert']").exists()).toBe(true);
    });

    it("explains a query with no clauses", async () => {
        const wrapper = mountForm({});
        await wrapper
            .find("#abac-search-query")
            .setValue(
                '{"graph_slug": "monument", "clauses": [], "groups": []}',
            );
        expect(lastDefinition(wrapper)).toEqual({});
        expect(wrapper.find("[role='alert']").text()).toContain(
            "at least one clause",
        );
    });

    it("clears the definition when the text is emptied", async () => {
        const wrapper = mountForm({ advanced_search_query: QUERY });
        await wrapper.find("#abac-search-query").setValue("  ");
        expect(lastDefinition(wrapper)).toEqual({});
        expect(wrapper.find("[role='alert']").exists()).toBe(false);
    });

    it("reloads the text when another rule is selected", async () => {
        const wrapper = mountForm({});
        await wrapper.find("#abac-search-query").setValue("{ not json");
        const other = { ...QUERY, graph_slug: "place" };
        await wrapper.setProps({
            modelValue: { advanced_search_query: other },
        });
        expect(JSON.parse(textarea(wrapper).value)).toEqual(other);
        expect(wrapper.find("[role='alert']").exists()).toBe(false);
    });
});
