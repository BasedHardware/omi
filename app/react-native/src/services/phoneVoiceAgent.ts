import { create } from 'zustand';
import { createActionItem } from '@/api/omiApi';
import { GUEST_MODE } from '@/devFlags';
import { runAgent } from './localAgent';
import { answerLocally } from './localAssistant';
import { tts } from './tts';
import { bestEffortWords, utteranceFrom } from './voiceAgent';
import { useAuthStore } from '@/state/authStore';
import { useCaptureStore } from '@/state/captureStore';

export type PhoneVoiceAgentStatus =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'error';

interface PhoneVoiceAgentState {
  status: PhoneVoiceAgentStatus;
  error: string | null;
  heard: string | null;
  reply: string | null;
  /** Start listening on the phone mic for a voice turn. */
  startListening: () => void;
  /** Stop listening, run the local agent, and speak the reply. */
  stopAndRespond: () => Promise<void>;
  /** Toggle: idle -> listen, listening -> respond, other busy states no-op. */
  toggle: () => void;
  cancel: () => void;
}

let responding = false;

export const usePhoneVoiceAgentStore = create<PhoneVoiceAgentState>((set, get) => ({
  status: 'idle',
  error: null,
  heard: null,
  reply: null,

  startListening: () => {
    const st = get();
    if (st.status === 'listening' || st.status === 'thinking' || st.status === 'speaking') return;
    const capture = useCaptureStore.getState();
    if (capture.recording || capture.connecting) return;
    set({ status: 'listening', error: null, heard: null, reply: null });
    capture.start();
    // If start failed synchronously (e.g. no token), captureStore sets error.
    const err = useCaptureStore.getState().error;
    if (err) {
      set({ status: 'error', error: err });
    }
  },

  stopAndRespond: async () => {
    if (responding) return;
    responding = true;
    try {
      const capture = useCaptureStore.getState();
      let words = utteranceFrom(capture.segments);
      if (capture.recording || capture.connecting) {
        capture.stop();
        const snap = useCaptureStore.getState().lastSegments;
        words = words || utteranceFrom(snap) || bestEffortWords(snap);
      } else if (!words) {
        words = utteranceFrom(capture.lastSegments) || bestEffortWords(capture.lastSegments);
      }

      if (!words) {
        set({ status: 'idle', error: 'No speech captured. Tap the mic and try again.' });
        return;
      }

      set({ status: 'thinking', error: null, heard: words });
      const action = await runAgent(words);
      const uid = useAuthStore.getState().uid;
      let reply: string;

      if (action.kind === 'chat') {
        const answer = await answerLocally(words);
        reply = answer.text;
      } else {
        if (!uid && !GUEST_MODE) {
          reply = 'Sign in so I can save that to your account.';
        } else {
          if (action.kind === 'create_reminder' && action.minutesFromNow) {
            await createActionItem(action.title, {
              due_at: new Date(Date.now() + action.minutesFromNow * 60_000).toISOString(),
            });
            reply = `Reminder set in ${action.minutesFromNow} minutes: ${action.title}`;
          } else if (action.kind === 'create_reminder') {
            await createActionItem(action.title);
            reply = `Reminder set: ${action.title}`;
          } else {
            await createActionItem(action.title);
            reply = `Task added: ${action.title}`;
          }
        }
      }

      set({ status: 'speaking', reply });
      await tts.speak(reply);
      set({ status: 'idle' });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      set({ status: 'error', error: message });
    } finally {
      responding = false;
    }
  },

  toggle: () => {
    const st = get();
    if (st.status === 'idle' || st.status === 'error') {
      st.startListening();
      return;
    }
    if (st.status === 'listening') {
      void st.stopAndRespond();
    }
  },

  cancel: () => {
    const capture = useCaptureStore.getState();
    if (capture.recording || capture.connecting) {
      capture.stop();
    }
    void tts.stop();
    responding = false;
    set({ status: 'idle', error: null });
  },
}));
