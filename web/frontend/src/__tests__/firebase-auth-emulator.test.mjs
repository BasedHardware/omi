/**
 * Behavioral coverage for the Firebase Auth emulator gate. These tests call the
 * production resolver directly — the same function `src/lib/firebase.ts` uses to
 * decide whether to call `connectAuthEmulator`.
 *
 * Run: cd web/frontend && npm test
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { resolveAuthEmulatorUrl } from '../lib/firebase-auth-emulator.mjs';

describe('resolveAuthEmulatorUrl', () => {
  it('is off when the host is unset', () => {
    assert.equal(resolveAuthEmulatorUrl({ NODE_ENV: 'development' }), null);
    assert.equal(
      resolveAuthEmulatorUrl({
        NODE_ENV: 'development',
        NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST: '   ',
      }),
      null,
    );
  });

  it('connects for a loopback host in a non-production build', () => {
    assert.equal(
      resolveAuthEmulatorUrl({
        NODE_ENV: 'development',
        NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST: '127.0.0.1:9099',
      }),
      'http://127.0.0.1:9099',
    );
    assert.equal(
      resolveAuthEmulatorUrl({
        NODE_ENV: 'test',
        NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST: 'http://localhost:9099/',
      }),
      'http://localhost:9099',
    );
  });

  it('never connects from a production build, even with a loopback host', () => {
    assert.equal(
      resolveAuthEmulatorUrl({
        NODE_ENV: 'production',
        NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST: '127.0.0.1:9099',
      }),
      null,
    );
  });

  it('refuses a non-loopback or malformed host', () => {
    for (const host of [
      'auth.example.com:9099',
      '10.0.0.5:9099',
      '127.0.0.1',
      '127.0.0.1:notaport',
      ':9099',
    ]) {
      assert.equal(
        resolveAuthEmulatorUrl({
          NODE_ENV: 'development',
          NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST: host,
        }),
        null,
        `expected ${host} to be refused`,
      );
    }
  });
});
