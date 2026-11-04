/**
 * voiceAgent's decision core is pure on purpose: what opens a session, which
 * words the agent acts on, and how the outcome is phrased. The BLE/socket work
 * around it is the part a device test covers.
 *
 * The module-load side effects (firebase auth store, capture store, expo-audio
 * TTS) are stubbed at the boundary; none of the functions under test touch them.
 */
jest.mock('@/state/authStore', () => ({ useAuthStore: { getState: () => ({ uid: null }) } }));
jest.mock('@/state/captureStore', () => ({ useCaptureStore: { getState: () => ({}) } }));
jest.mock('./tts', () => ({ tts: { speak: jest.fn(), speakOnOmi: jest.fn() } }));
jest.mock('./localAssistant', () => ({ answerLocally: jest.fn() }));
// The shipped default is guest-mode ON (uid null is a normal state, saves just
// 401 later). Pin it off here so the sign-in branch of replyFor is exercised;
// guest-on behavior is covered by the run:true cases below with an explicit uid.
jest.mock('@/devFlags', () => ({ GUEST_MODE: false }));

import { decodeButtonEvent, BUTTON_EVENT } from './omiBle';
import { replyFor, togglesSession, utteranceFrom } from './voiceAgent';
import type { TranscriptSegment } from './stt';

const seg = (over: Partial<TranscriptSegment>): TranscriptSegment =>
  ({
    text: 'hello',
    speaker: 'SPEAKER_00',
    isUser: false,
    start: 0,
    end: 1,
    isFinal: true,
    ...over,
  }) as TranscriptSegment;

describe('decodeButtonEvent', () => {
  const notify = (code: number) => {
    const b = new Uint8Array(8);
    new DataView(b.buffer).setInt32(0, code, true);
    return b;
  };

  it('reads the int32 LE event code firmware writes', () => {
    expect(decodeButtonEvent(notify(BUTTON_EVENT.doubleTap))).toBe(2);
    expect(decodeButtonEvent(notify(BUTTON_EVENT.singleTap))).toBe(1);
  });

  it('returns null on a truncated read rather than guessing', () => {
    expect(decodeButtonEvent(new Uint8Array(2))).toBeNull();
  });
});

describe('togglesSession', () => {
  it('only the double-tap toggles; long press is power-off, edges are noise', () => {
    for (const code of [
      BUTTON_EVENT.singleTap,
      BUTTON_EVENT.longTap,
      BUTTON_EVENT.press,
      BUTTON_EVENT.release,
    ]) {
      expect(togglesSession(code)).toBe(false);
    }
    expect(togglesSession(BUTTON_EVENT.doubleTap)).toBe(true);
  });
});

describe('utteranceFrom', () => {
  it('joins final, non-empty segments and drops partials', () => {
    const words = utteranceFrom([
      seg({ text: 'add a task: buy bread' }),
      seg({ text: '   ', isFinal: true }),
      seg({ text: 'partial thought', isFinal: false }),
    ]);
    expect(words).toBe('add a task: buy bread');
  });

  it('returns empty for a session with nothing final', () => {
    expect(utteranceFrom([seg({ isFinal: false })])).toBe('');
  });
});

describe('replyFor', () => {
  it('asks for sign-in only when an action needs saving', () => {
    const r = replyFor({ kind: 'create_task', title: 'x' }, null);
    expect(r.run).toBe(false);
    expect(r.text).toMatch(/sign in/i);
  });

  it('phrases task and reminder outcomes as short spoken sentences', () => {
    expect(replyFor({ kind: 'create_task', title: 'buy bread' }, 'uid').text).toBe(
      'Task added: buy bread'
    );
    const rem = replyFor({ kind: 'create_reminder', title: 'stretch', minutesFromNow: 20 }, 'uid');
    expect(rem.text).toContain('in 20 minutes');
    expect(rem.text).toContain('stretch');
  });

  it('leaves chat questions to the caller (recall answer)', () => {
    const r = replyFor({ kind: 'chat', text: 'what did marco say' }, 'uid');
    expect(r.run).toBe(true);
    expect(r.text).toBe('');
  });
});
