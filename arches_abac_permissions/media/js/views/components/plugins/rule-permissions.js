import ko from "knockout";

import RulePermissions from "@/arches_abac_permissions/plugins/RulePermissions/RulePermissions.vue";
import { ABAC_THEME } from "@/arches_abac_permissions/themes/default.ts";
import { createVueApplication } from "@/arches_vue_components/application";
import RulePermissionsTemplate from "templates/views/components/plugins/rule-permissions.htm";

ko.components.register("rule-permissions", {
    viewModel: function () {
        createVueApplication({
            component: RulePermissions,
            themeConfiguration: ABAC_THEME,
        }).then((vueApp) => {
            vueApp.mount("#rule-permissions-mounting-point");
        });
    },
    template: RulePermissionsTemplate,
});
