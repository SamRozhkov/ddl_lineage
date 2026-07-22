import React from 'react';

import en from './language/en.json';
import {getLanguagePack, isLanguageRegistered, resolvePlural, subscribeToLanguages} from './language';

export type Lang = string;

const STORAGE_KEY = 'ddl-lineage-lang';
const FALLBACK_LANG = 'en';

export type TranslationKey = keyof typeof en.strings | (string & {});
export type PluralKey = keyof typeof en.plurals | (string & {});

function detectDefaultLang(): Lang {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved && isLanguageRegistered(saved)) return saved;
    } catch {
        // ignore
    }
    const navCode =
        typeof navigator !== 'undefined' ? navigator.language?.toLowerCase().split('-')[0] : '';
    if (navCode && isLanguageRegistered(navCode)) return navCode;
    return FALLBACK_LANG;
}

function translate(lang: Lang, key: TranslationKey, vars?: Record<string, string | number>): string {
    const template =
        getLanguagePack(lang)?.strings[key] ?? getLanguagePack(FALLBACK_LANG)?.strings[key] ?? key;
    if (!vars) return template;
    return template.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? ''));
}

function pluralWord(lang: Lang, n: number, key: PluralKey): string {
    const pack = getLanguagePack(lang) ?? getLanguagePack(FALLBACK_LANG);
    const forms = pack?.plurals?.[key] ?? getLanguagePack(FALLBACK_LANG)?.plurals?.[key];
    if (!forms) return String(n);
    return resolvePlural(pack?.meta.pluralRule ?? 'one-other', n, forms);
}

interface I18nContextValue {
    lang: Lang;
    setLang: (lang: Lang) => void;
    t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
    plural: (n: number, key: PluralKey) => string;
}

const I18nContext = React.createContext<I18nContextValue | null>(null);

export const LanguageProvider: React.FC<{children: React.ReactNode}> = ({children}) => {
    const [lang, setLangState] = React.useState<Lang>(detectDefaultLang);
    // Bumped whenever a language pack is registered/patched at runtime, so
    // consumers re-render even when `lang` itself hasn't changed.
    const [registryVersion, setRegistryVersion] = React.useState(0);

    React.useEffect(() => subscribeToLanguages(() => setRegistryVersion((v) => v + 1)), []);

    const setLang = React.useCallback((next: Lang) => {
        setLangState(next);
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch {
            // ignore
        }
    }, []);

    const t = React.useCallback(
        (key: TranslationKey, vars?: Record<string, string | number>) => translate(lang, key, vars),
        [lang],
    );

    const plural = React.useCallback((n: number, key: PluralKey) => pluralWord(lang, n, key), [lang]);

    const value = React.useMemo(
        () => ({lang, setLang, t, plural}),
        [lang, setLang, t, plural, registryVersion],
    );

    return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export function useI18n(): I18nContextValue {
    const ctx = React.useContext(I18nContext);
    if (!ctx) throw new Error('useI18n must be used within a LanguageProvider');
    return ctx;
}

export function formatRelativeTime(isoString: string, t: I18nContextValue['t']): string {
    try {
        const diff = Date.now() - new Date(isoString).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return t('time.justNow');
        if (mins < 60) return t('time.minutesAgo', {n: mins});
        const hours = Math.floor(mins / 60);
        if (hours < 24) return t('time.hoursAgo', {n: hours});
        return t('time.daysAgo', {n: Math.floor(hours / 24)});
    } catch {
        return '';
    }
}

export {registerLanguage, getAvailableLanguages} from './language';
export type {LanguagePack} from './language';
