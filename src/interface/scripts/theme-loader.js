const ThemeLoader = (() => {
    const STORAGE_KEY = 'claudefm_theme';
    const DEFAULT_THEME = 'dark';
    const THEMES_PATH = '../assets/themes/';

    let currentTheme = null;

    async function load(themeName) {
        try {
            const res = await fetch(`${THEMES_PATH}${themeName}.json`);
            if (!res.ok) throw new Error(`Theme not found: ${themeName}`);
            const theme = await res.json();
            apply(theme);
            currentTheme = themeName;
            localStorage.setItem(STORAGE_KEY, themeName);
        } catch (err) {
            console.error('ThemeLoader:', err);
            if (themeName !== DEFAULT_THEME) load(DEFAULT_THEME);
        }
    }

    function apply(theme) {
        const root = document.documentElement;
        const { colors, typography } = theme;

        const map = {
            '--color-bg-base':     colors.bg_base,
            '--color-bg-surface':  colors.bg_surface,
            '--color-bg-elevated': colors.bg_elevated,
            '--color-bg-card':     colors.bg_card,
            '--color-bg-input':    colors.bg_input,

            '--color-accent':        colors.accent,
            '--color-accent-dark':   colors.accent_dark,
            '--color-accent-text':   colors.accent_text,

            '--color-text-primary':   colors.text_primary,
            '--color-text-secondary': colors.text_secondary,
            '--color-text-muted':     colors.text_muted,
            '--color-text-on-accent': colors.text_on_accent,

            '--color-border':       colors.border,
            '--color-border-light': colors.border_light,
            '--color-separator':    colors.separator,

            '--color-error':   colors.error,
            '--color-warning': colors.warning,
            '--color-info':    colors.info,
            '--color-success': colors.success,

            '--shadow-heavy':  `0px 8px 24px ${colors.shadow_heavy}`,
            '--shadow-medium': `0px 8px 8px ${colors.shadow_medium}`,
            '--shadow-light':  `0px 4px 4px ${colors.shadow_light}`,
            '--shadow-inset':  `rgb(18,18,18) 0px 1px 0px, ${colors.border_light} 0px 0px 0px 1px inset`,

            '--color-overlay':     colors.overlay,
            '--color-player-bg':   colors.player_bg,
            '--color-topbar-bg':   colors.topbar_bg,
            '--color-sidebar-bg':  colors.sidebar_bg,

            '--font-family':       typography.font_family,
            '--font-family-title': typography.font_family_title,
        };

        for (const [prop, value] of Object.entries(map)) {
            root.style.setProperty(prop, value);
        }

        document.documentElement.setAttribute('data-theme', theme.name);
    }

    function toggle() {
        const next = currentTheme === 'dark' ? 'light' : 'dark';
        load(next);
    }

    function init() {
        const saved = localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
        load(saved);
    }

    return { init, load, toggle, get current() { return currentTheme; } };
})();

document.addEventListener('DOMContentLoaded', () => ThemeLoader.init());
