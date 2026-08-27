/**
 * Import boundaries for src/features and src/shared.
 *
 * - shared must not import features
 * - a feature's model.ts must not import React or that feature's api
 * - code outside a feature may only import its public root (@/features/<name>)
 */
import { readdir, readFile } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';

const root = join(import.meta.dir, '..');
const srcRoot = join(root, 'src');

const IMPORT_RE =
  /(?:from|import)\s*\(\s*['"]([^'"]+)['"]\s*\)|(?:from|import)\s+['"]([^'"]+)['"]|export\s+\*\s+from\s+['"]([^'"]+)['"]/g;

async function walk(dir: string): Promise<string[]> {
  const out: string[] = [];
  for (const ent of await readdir(dir, { withFileTypes: true })) {
    if (ent.name.startsWith('.') || ent.name === 'node_modules') continue;
    const p = join(dir, ent.name);
    if (ent.isDirectory()) out.push(...(await walk(p)));
    else if (['.ts', '.tsx', '.js', '.jsx'].includes(extname(ent.name))) out.push(p);
  }
  return out;
}

function featureOf(file: string): string | null {
  const rel = relative(srcRoot, file).replaceAll('\\', '/');
  const m = rel.match(/^features\/([^/]+)\//);
  return m ? m[1] : null;
}

function isShared(file: string): boolean {
  return relative(srcRoot, file).replaceAll('\\', '/').startsWith('shared/');
}

function isModel(file: string): boolean {
  return /(?:^|\/)model\.ts$/.test(relative(srcRoot, file).replaceAll('\\', '/'));
}

function specs(text: string): string[] {
  const found: string[] = [];
  for (const m of text.matchAll(IMPORT_RE)) {
    const spec = m[1] || m[2] || m[3];
    if (spec) found.push(spec);
  }
  return found;
}

const errors: string[] = [];
const files = await walk(srcRoot);

for (const file of files) {
  const rel = relative(root, file);
  const text = await readFile(file, 'utf8');
  const fromFeature = featureOf(file);
  const model = isModel(file);

  for (const spec of specs(text)) {
    if (
      isShared(file) &&
      (spec.startsWith('@/features/') || spec.includes('/features/'))
    ) {
      errors.push(`${rel} (shared) imports ${spec}`);
    }

    if (
      model &&
      (spec === 'react' || spec.startsWith('react/') || spec === 'react-dom')
    ) {
      errors.push(`${rel} (model) imports React (${spec})`);
    }
    if (
      model &&
      (spec === './api' || spec.endsWith('/api') || spec === '@/shared/api/client')
    ) {
      errors.push(`${rel} (model) imports API (${spec})`);
    }

    const featImport = spec.match(/^@\/features\/([^/]+)(?:\/(.*))?$/);
    if (featImport) {
      const name = featImport[1];
      const rest = featImport[2] ?? '';
      const publicFile =
        rest === '' ||
        rest === 'index' ||
        rest === 'index.ts' ||
        rest === 'index.tsx' ||
        rest === 'api' ||
        rest === 'api.ts' ||
        rest === 'model' ||
        rest === 'model.ts';
      if (!publicFile && fromFeature !== name) {
        errors.push(
          `${rel} imports @/features/${name}/${rest}; outside the feature use @/features/${name}, api, or model`,
        );
      }
    }
  }
}

if (errors.length) {
  console.error(
    'Feature import boundary violations:\n' + errors.map((e) => `  ${e}`).join('\n'),
  );
  process.exit(1);
}

console.log(`ok: ${files.length} files, feature import boundaries hold`);
