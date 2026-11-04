import { definePreset } from "@openvue/themes";

import {
    ArchesPreset,
    DEFAULT_THEME,
} from "@/arches_vue_components/themes/default.ts";

import type { ArchesThemeConfiguration } from "@/arches_vue_components/themes/types";

// Plugin palette; emitted as --p-abac-* custom properties.
export const AbacPreset = definePreset(ArchesPreset, {
    semantic: {
        colorScheme: {
            light: {
                abac: {
                    surfaceBg: "#f5f6fa",
                    surfaceCard: "#ffffff",
                    border: "#dde2ef",
                    textPrimary: "#1a2236",
                    textSecondary: "#5a6a8a",
                    accent: "#4a90d9",
                    accentSubtle: "#b8d4f0",
                    accentTint: "rgba(74, 144, 217, 0.1)",
                    rowHover: "#e8f2fb",
                    brandLight: "#3d5499",
                    danger: "#e53e3e",
                    dangerTint: "rgba(229, 62, 62, 0.1)",
                    statusActiveBg: "#f0fdf4",
                    statusActiveText: "#166534",
                    statusActiveBorder: "#bbf7d0",
                },
            },
            dark: {
                abac: {
                    surfaceBg: "#151b28",
                    surfaceCard: "#1d2535",
                    border: "#2f3a52",
                    textPrimary: "#e6eaf3",
                    textSecondary: "#9aa8c4",
                    accent: "#6aa8e6",
                    accentSubtle: "#2d4f75",
                    accentTint: "rgba(106, 168, 230, 0.16)",
                    rowHover: "#22334a",
                    brandLight: "#8ea4e6",
                    danger: "#f87171",
                    dangerTint: "rgba(248, 113, 113, 0.16)",
                    statusActiveBg: "#12301f",
                    statusActiveText: "#86efac",
                    statusActiveBorder: "#1f5133",
                },
            },
        },
    },
});

export const ABAC_THEME = {
    theme: { ...DEFAULT_THEME.theme, preset: AbacPreset },
} satisfies ArchesThemeConfiguration;
