import assert from 'node:assert/strict';
import test from 'node:test';

import { isSafeDocumentId } from '../firestore-doc-id.mjs';

test('accepts ordinary Firestore ids', () => {
  assert.equal(isSafeDocumentId('abc123'), true);
  assert.equal(isSafeDocumentId('user-with-dash_and.dots'), true);
});

test('accepts ids with characters encodeURIComponent would rewrite', () => {
  // Firebase uids from custom auth may contain these; the stored doc id must
  // match the raw value, so they must pass through unchanged.
  assert.equal(isSafeDocumentId('google:abc123'), true);
  assert.equal(isSafeDocumentId('user@example.com'), true);
  assert.equal(isSafeDocumentId('uid+plus@x'), true);
  assert.equal(isSafeDocumentId('uid?query'), true);
  assert.equal(isSafeDocumentId('uid%40x'), true);
  assert.equal(isSafeDocumentId('user name'), true);
});

test('rejects ids that split a Firestore path', () => {
  assert.equal(isSafeDocumentId('a/b'), false);
  assert.equal(isSafeDocumentId('a/b/c/d'), false);
});

test('rejects empty and Firestore-reserved ids', () => {
  assert.equal(isSafeDocumentId(''), false);
  assert.equal(isSafeDocumentId('.'), false);
  assert.equal(isSafeDocumentId('..'), false);
  assert.equal(isSafeDocumentId('__name__'), false);
  assert.equal(isSafeDocumentId('__x__'), false);
});

test('rejects non-strings', () => {
  assert.equal(isSafeDocumentId(undefined), false);
  assert.equal(isSafeDocumentId(null), false);
  assert.equal(isSafeDocumentId(42), false);
});
