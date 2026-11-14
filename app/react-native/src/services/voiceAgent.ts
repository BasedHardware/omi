/**
 * "Press twice, talk, it answers" - the voice-agent session driven by the
 * wearable's physical button.
 *
 * The stock DevKit 2 firmware already sends DOUBLE_TAP (code 2) over the button
 * characteristic, so this needs no new firmware: it turns the existing device
 * event into a capture session:
 *
 *   double-tap #1  device mic -> BLE -> backend STT socket (captureStore)
 *   you speak      transcripts stream in as segments
 *   double-tap #2  session closes; the words go to the local agent:
 *                  "add a task / remind me to ..." -> creates an action item,
 *                  anything else -> on-device recall (answerLocally).
 *   reply spoken   DevKit 2 speaker when the backend honors ulaw_8000, phone
 *                  TTS otherwise (see tts.speakOnOmi's MP3 guard).
 *
 * Deliberately NOT treated: code 3 (long press) - that is power-off on the
 * device, and codes 4/5 (press/release edges) which fire on every gesture.
 */
import { create } from 'zustand';
import { createActionItem } from '@/api/omiApi';
import { useAuthStore } from '@/state/authStore';
import { useCaptureStore } from '@/state/captureStore';
import { GUEST_MODE } from '@/devFlags';
import { runAgent, type AgentAction } from './localAgent';
import { answerLocally } from './localAssistant';
import { BUTTON_EVENT, omiBle } from './omiBle';
import { tts } from './tts';
import type { TranscriptSegment } from './stt';

/** Pure: only a double-tap toggles a session. Exported for tests. */
export function togglesSession(code: number): boolean {
  return code === BUTTON_EVENT.doubleTap;
}

/** Pure: the words a finished session acts on (final, non-empty segments). */
export function utteranceFrom(segments: TranscriptSegment[]): string {
  return segments
    .filter((s) => s.isFinal && s.text.trim())
    .map((s) => s.text.trim())
    .join(' ')
    .trim();
}

/** Best-effort transcript when no finals arrived (e.g. stopped mid-utterance). */
export function bestEffortWords(segments: TranscriptSegment[]): string {
  const finals = utteranceFrom(segments);
  if (finals) return finals;
  const parts = segments
    .filter((s) => s.text.trim())
    .map((s) => s.text.trim());
  // Prefer the longest recent non-empty text to avoid duplicated interim fragments.
  let best = '';
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i] ?? '';
    if (p.length > best.length) best = p;
  }
  return best.trim();
}

/** Pure: how to phrase the agent outcome as speech. */
export function replyFor(action: AgentAction, uid: string | null): { text: string; run: boolean } {
  if (action.kind === 'chat') return { text: '', run: true };
  if (!uid && !GUEST_MODE) {
    return { text: 'Sign in so I can save that to your account.', run: false };
  }
  if (action.kind === 'create_task') {
    return { text: `Task added: ${action.title}`, run: true };
  }
  const when =
    action.minutesFromNow !== undefined ? ` in ${action.minutesFromNow} minutes` : '';
  return { text: `Reminder set${when}: ${action.title}`, run: true };
}

export interface VoiceAgentState {
  active: boolean;
  attached: boolean;
  status: string;
  lastReply: string | null;
  /** The transcript that was (or is being) sent to the agent, for UI. */
  lastHeard: string | null;
  /** Subscribes the wearable button to this session controller. */
  attach: () => Promise<boolean>;
  detach: () => void;
  /** Feed a raw button code (also called internally via attach). */
  handleTap: (code: number) => void;
  /** Stop capture (if any), run the local agent on the heard words, speak reply. */
  ask: () => Promise<void>;
  _start: () => Promise<void>;
  _finish: () => Promise<void>;
}

let starting = false;
let finishing = false;

export const useVoiceAgentStore = create<VoiceAgentState>((set, get) => ({
  active: false,
  attached: false,
  status: 'idle',
  lastReply: null,
  lastHeard: null,

  attach: async () => {
    if (get().attached) return true;
    try {
      await omiBle.onButton(
        (code) => get().handleTap(code),
        (e) => set({ status: `button listener error: ${String(e)}` })
      );
      set({ attached: true, status: 'double-tap the device to talk' });
      return true;
    } catch (e) {
      set({ status: `attach failed: ${e instanceof Error ? e.message : String(e)}` });
      return false;
    }
  },

  detach: () => {
    omiBle.stopButton();
    set({ attached: false, status: 'idle' });
  },

  handleTap: (code) => {
    if (!togglesSession(code)) return;
    const st = get();
    if (st.active) {
      // Second double-tap: close the session and act on what was heard.
      void st.ask();
      return;
    }
    // Reentrancy guard: _start is async (identity read + socket connect), and a
    // second tap landing mid-start would otherwise double-open a session.
    if (starting) return;
    starting = true;
    void st
      ._start()
      .catch((e) => set({ status: `start failed: ${String(e)}` }))
      .finally(() => {
        starting = false;
      });
  },

  _start: async () => {
    set({ active: true, status: 'listening... (double-tap again, or tap "Send to agent")' });
    const identity = await omiBle.readIdentity();
    const capture = useCaptureStore.getState();
    capture.startFromOmi(identity.codec);
    const err = useCaptureStore.getState().error;
    if (err) {
      set({ active: false, status: err });
    }
  },

  ask: async () => {
    if (finishing) return;
    finishing = true;
    try {
      await get()._finish();
    } finally {
      finishing = false;
    }
  },

  _finish: async () => {
    // Flip active synchronously: the await below must not leave a window where
    // another tap reopens or double-finishes this session.
    set({ active: false, status: 'thinking...' });
    const capture = useCaptureStore.getState();
    let words = utteranceFrom(capture.segments);
    if (capture.recording || capture.connecting) {
      capture.stop();
      // Prefer the snapshot we just stopped (now in lastSegments) if needed.
      const snap = useCaptureStore.getState().lastSegments;
      words = words || utteranceFrom(snap) || bestEffortWords(snap);
    } else if (!words) {
      words = utteranceFrom(capture.lastSegments) || bestEffortWords(capture.lastSegments);
    }
    if (!words) {
      set({ status: 'no speech captured (say something, then tap "Send to agent")', lastHeard: null });
      return;
    }
    set({ status: `heard: "${words}"`, lastHeard: words });
    try {
      const action = await runAgent(words);
      const uid = useAuthStore.getState().uid;
      const plan = replyFor(action, uid);
      if (!plan.run) {
        await speak(plan.text);
        set({ lastReply: plan.text, status: plan.text });
        return;
      }
      let reply: string;
      if (action.kind === 'chat') {
        const answer = await answerLocally(words);
        reply = answer.text;
      } else {
        if (action.kind === 'create_reminder' && action.minutesFromNow) {
          await createActionItem(action.title, {
            due_at: new Date(Date.now() + action.minutesFromNow * 60_000).toISOString(),
          });
        } else {
          await createActionItem(action.title);
        }
        reply = plan.text;
      }
      set({ lastReply: reply, status: `reply: ${reply}` });
      await speak(reply);
    } catch (e) {
      set({ status: `agent failed: ${e instanceof Error ? e.message : String(e)}` });
    }
  },
}));

async function speak(text: string): Promise<void> {
  if (!text) return;
  const device = await tts.speakOnOmi(text);
  if (!device) await tts.speak(text);
}
