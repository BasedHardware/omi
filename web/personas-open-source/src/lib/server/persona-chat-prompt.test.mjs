import assert from 'node:assert/strict';
import test from 'node:test';

import { buildPersonaSystemPrompt } from './persona-chat-prompt.mjs';

test('persona prompt keeps the selected persona identity while applying Luna style guidance', () => {
  const prompt = buildPersonaSystemPrompt('You are Ada, an AI persona.');

  assert.match(prompt, /Be warm and perceptive/);
  assert.match(prompt, /You are Ada, an AI persona\.$/);
  assert.doesNotMatch(prompt, /You are Omi/);
});
