import en from './en.json';
import ru from './ru.json';

export type PluralRule = 'one-other' | 'ru';

export interface LanguagePack {
    meta: {
        name: string;
        pluralRule: PluralRule;
    };
    strings: Record<string, string>;
    plurals?: Record<string, string[]>;
}

const PLURAL_RESOLVERS: Record<PluralRule, (n: number, forms: string[]) => string> = {
    'one-other': (n, forms) => forms[n === 1 ? 0 : 1] ?? forms[forms.length - 1],
    ru: (n, forms) => {
        const abs = Math.abs(n) % 100;
        const mod10 = abs % 10;
        if (abs > 10 && abs < 20) return forms[2] ?? forms[forms.length - 1];
        if (mod10 === 1) return forms[0];
        if (mod10 >= 2 && mod10 <= 4) return forms[1] ?? forms[forms.length - 1];
        return forms[2] ?? forms[forms.length - 1];
    },
};

const registry = new Map<string, LanguagePack>();
const listeners = new Set<() => void>();

function notify() {
    listeners.forEach((cb) => cb());
}

function mergePack(existing: LanguagePack | undefined, pack: LanguagePack): LanguagePack {
    if (!existing) return pack;
    return {
        meta: {...existing.meta, ...pack.meta},
        strings: {...existing.strings, ...pack.strings},
        plurals: {...existing.plurals, ...pack.plurals},
    };
}

/**
 * Registers a language pack, merging it into any pack already registered under
 * the same code. Call this to add a brand-new language at runtime, or to patch/
 * extend an existing one (e.g. a plugin contributing a handful of extra keys).
 */
export function registerLanguage(code: string, pack: LanguagePack): void {
    registry.set(code, mergePack(registry.get(code), pack));
    notify();
}

export function getLanguagePack(code: string): LanguagePack | undefined {
    return registry.get(code);
}

export function getAvailableLanguages(): Array<{code: string; name: string}> {
    return Array.from(registry.entries()).map(([code, pack]) => ({code, name: pack.meta.name}));
}

export function isLanguageRegistered(code: string): boolean {
    return registry.has(code);
}

export function subscribeToLanguages(callback: () => void): () => void {
    listeners.add(callback);
    return () => listeners.delete(callback);
}

export function resolvePlural(rule: PluralRule, n: number, forms: string[]): string {
    const resolver = PLURAL_RESOLVERS[rule] ?? PLURAL_RESOLVERS['one-other'];
    return resolver(n, forms);
}

registerLanguage('en', en as LanguagePack);
registerLanguage('ru', ru as LanguagePack);
