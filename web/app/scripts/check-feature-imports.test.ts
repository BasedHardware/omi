import { describe, expect, it } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';

const appRoot = join(import.meta.dir, '..');

describe('check-feature-imports', () => {
  it('passes on the current tree', () => {
    const result = spawnSync('bun', ['scripts/check-feature-imports.ts'], {
      cwd: appRoot,
      encoding: 'utf8',
    });
    expect(result.status).toBe(0);
    expect(result.stdout).toContain('ok:');
  });
});
