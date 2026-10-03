import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';
import {
  loadUiCatalog,
  resolveUiLanguage,
  setUiLanguageForTesting,
  t,
  tc,
  tn,
  translate,
} from '@/lib/i18n';
import es from '@/lib/i18n/es.json';

beforeAll(async () => {
  await loadUiCatalog('es');
});

const placeholders = (s: string): string[] => (s.match(/\{\w+\}/g) ?? []).sort();

describe('resolveUiLanguage', () => {
  it('honors an explicit preference over the browser language', () => {
    expect(resolveUiLanguage('es', ['en-US'])).toBe('es');
    expect(resolveUiLanguage('en', ['es-MX'])).toBe('en');
  });

  it('follows the first supported browser language when unset', () => {
    expect(resolveUiLanguage(null, ['fr-FR', 'es-419'])).toBe('es');
    expect(resolveUiLanguage('system', ['pt-BR', 'es-ES'])).toBe('es');
    expect(resolveUiLanguage(undefined, ['en-GB', 'es-ES'])).toBe('en');
  });

  it('falls back to English for unsupported or missing languages', () => {
    expect(resolveUiLanguage(null, ['fr-FR', 'de-DE'])).toBe('en');
    expect(resolveUiLanguage(null, [])).toBe('en');
  });
});

describe('translate', () => {
  it('returns English unchanged and falls back to it for missing keys', () => {
    expect(translate('en', 'Settings')).toBe('Settings');
    expect(translate('es', 'A string nobody translated')).toBe(
      'A string nobody translated',
    );
  });

  it('looks up the loaded catalogs and fills placeholders', () => {
    expect(translate('es', 'Search memories...')).toBe(es['Search memories...']);
    expect(translate('es', '{count} conversations', { count: 3 })).toBe(
      '3 conversaciones',
    );
  });

  it('tc uses a context-specific entry only when one exists', () => {
    setUiLanguageForTesting('es');
    expect(tc('no-such-context', 'Open')).toBe('Open');
    expect(t('Search memories...')).toBe(es['Search memories...']);
    setUiLanguageForTesting('en');
  });
});

describe('tn', () => {
  it('picks the singular only for exactly one and fills the count', () => {
    setUiLanguageForTesting('es');
    expect(tn(1, '{count} memory', '{count} memories')).toBe('1 recuerdo');
    expect(tn(0, '{count} memory', '{count} memories')).toBe('0 recuerdos');
    expect(tn(3, 'Delete {count} conversation?', 'Delete {count} conversations?')).toBe(
      '¿Eliminar 3 conversaciones?',
    );
    setUiLanguageForTesting('en');
    expect(tn(1, '{count} task needs a date', '{count} tasks need a date')).toBe(
      '1 task needs a date',
    );
  });
});

describe('UI sources', () => {
  const sourceFiles = (dir: string, out: string[] = []): string[] => {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) {
        if (name !== '__tests__') sourceFiles(full, out);
      } else if (/\.tsx?$/.test(name)) out.push(full);
    }
    return out;
  };

  it('never glue an English plural "s" onto text (use tn with whole sentences)', () => {
    const offenders = sourceFiles(path.join(import.meta.dirname, '..', '..')).filter(
      (file) => /\?\s*'e?s'\s*:\s*''/.test(readFileSync(file, 'utf8')),
    );
    expect(offenders).toEqual([]);
  });
});

describe('Spanish catalog', () => {
  it('has a non-empty translation with the same placeholders for every key', () => {
    for (const [key, value] of Object.entries(es as Record<string, string>)) {
      expect(value.trim(), key).not.toBe('');
      expect(placeholders(value), key).toEqual(placeholders(key.split('|').pop() ?? key));
    }
  });
});
