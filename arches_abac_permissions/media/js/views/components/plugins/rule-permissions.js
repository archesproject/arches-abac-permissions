import ko from 'knockout';

import { ArchesPreset, DEFAULT_THEME } from '@/arches/themes/default.ts';
import RulePermissions from '@/arches_abac_permissions/plugins/RulePermissions.vue';
import { createVueApplication } from '@/arches_vue_components/application';
import RulePermissionsTemplate from 'templates/views/components/plugins/rule-permissions.htm';

ko.components.register('rule-permissions', {
    viewModel: function() {
        createVueApplication({
            component: RulePermissions,
            themeConfiguration: { theme: { ...DEFAULT_THEME.theme, preset: ArchesPreset } },
        }).then((vueApp) => {
            vueApp.mount('#rule-permissions-mounting-point');
        });
    },
    template: RulePermissionsTemplate,
});
