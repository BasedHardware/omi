import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { AlertTriangle, ArrowUp, Loader2, Mic, X } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useAuthStore } from "@/stores/authStore";
import { GenerativeMarkdown } from "@/components/generative-ui/GenerativeMarkdown";
import { Waveform } from "@/components/transcript/Waveform";
import {
  SpeakerBubbles,
  type LiveSegment,
} from "@/components/transcript/SpeakerBubbles";
import { AudioSourceSelector } from "@/components/transcript/AudioSourceSelector";
import { LiveNameSpeakerSheet } from "@/components/transcript/LiveNameSpeakerSheet";
import "./FloatingBar.css";

type Mode = "pill" | "input" | "response" | "listening" | "alert";

interface AlertPayload {
  title: string;
  body: string;
}

const ALERT_AUTO_HIDE_MS = 6000;


export function FloatingBar() {
  // The floating window is only ever shown on an explicit user action
  // (shortcut or tray click), so boot into the input mode with the
  // textarea ready — no idle pill intermediate state.
  const [mode, setMode] = useState<Mode>("input");
  const [draft, setDraft] = useState("");
  const [liveTranscript, setLiveTranscript] = useState("");
  const [liveSegments, setLiveSegments] = useState<LiveSegment[]>([]);
  const [livePartial, setLivePartial] = useState<Record<string, string>>({});
  const [identifyingSpeaker, setIdentifyingSpeaker] = useState<
    { speaker: string; speakerId: number; sampleText: string } | null
  >(null);
  const [alert, setAlert] = useState<AlertPayload | null>(null);
  const alertTimerRef = useRef<number | null>(null);

  const restoreSession = useAuthStore((s) => s.restoreSession);
  const isSignedIn = useAuthStore((s) => s.isSignedIn);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const messages = useChatStore((s) => s.messages);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // Live transcript accumulates finalized segments as they arrive so we can
  // show them immediately; the ptt-final event is authoritative for sending.
  const finalSegmentsRef = useRef<string[]>([]);
  const interimRef = useRef<string>("");
  // PTT session timing so we can log how long the user held the key.

  // Bootstrap auth for this window (each Tauri window has its own JS runtime).
  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  // PTT event bridge. The Rust side (commands/ptt.rs) detects the Option/Alt
  // hold globally and asks us to start/stop the audio-capture plugin. The
  // plugin streams transcripts back via `transcript:partial` and signals the
  // end of a PTT session via `transcript:ptt-final`.
  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    listen("floating:activate", () => {
      // Hotkey invoked — jump straight into the input state, ready to type.
      // Clear any stale draft so the textarea is empty and waiting.
      setDraft("");
      setMode((current) => (current === "listening" ? current : "input"));
      // Re-focus on the next frame; the window just showed, so React's
      // textarea is either already mounted or about to be.
      requestAnimationFrame(() => {
        textareaRef.current?.focus();
      });
    }).then((fn) => unlisteners.push(fn));

    // PTT dictation is handled by the dedicated Whispr HUD window. The
    // chat floating bar stays in its current mode during dictation.

    listen<AlertPayload>("floating:alert", (e) => {
      setAlert(e.payload);
      setMode("alert");
      if (alertTimerRef.current != null) {
        window.clearTimeout(alertTimerRef.current);
      }
      alertTimerRef.current = window.setTimeout(() => {
        setMode((current) => (current === "alert" ? "pill" : current));
        setAlert(null);
        invoke("hide_floating_bar").catch(() => {});
        alertTimerRef.current = null;
      }, ALERT_AUTO_HIDE_MS);
    }).then((fn) => unlisteners.push(fn));

    listen("transcript:ptt-final", () => {
      // The Rust side handles the paste into the focused app. We just
      // clear any visual listening state if the floating bar was open.
      interimRef.current = "";
      finalSegmentsRef.current = [];
      setLiveTranscript("");
      setLiveSegments([]);
      setLivePartial({});
      setMode((current) => (current === "listening" ? "pill" : current));
    }).then((fn) => unlisteners.push(fn));

    return () => {
      unlisteners.forEach((fn) => fn());
      if (alertTimerRef.current != null) {
        window.clearTimeout(alertTimerRef.current);
        alertTimerRef.current = null;
      }
    };
  }, [sendMessage]);

  // Sync Tauri window height to rendered content.
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    let frame = 0;
    const push = () => {
      frame = 0;
      const height = Math.ceil(el.getBoundingClientRect().height);
      if (height > 0) invoke("resize_floating_bar", { height }).catch(() => {});
    };
    const schedule = () => {
      if (frame) return;
      frame = requestAnimationFrame(push);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(el);
    schedule();
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  // Focus the textarea when entering input mode. Defer to the next frame so
  // the textarea is actually mounted in the DOM before we try to focus it —
  // without this, set_focus() on the window races with React's render.
  useEffect(() => {
    if (mode !== "input") return;
    invoke("focus_floating_bar").catch(() => {});
    const raf = requestAnimationFrame(() => {
      textareaRef.current?.focus();
      // Cursor at end if there's existing draft text.
      const el = textareaRef.current;
      if (el) el.setSelectionRange(el.value.length, el.value.length);
    });
    return () => cancelAnimationFrame(raf);
  }, [mode]);

  // When a response starts streaming, switch to response mode.
  useEffect(() => {
    if (isStreaming && mode === "input") setMode("response");
  }, [isStreaming, mode]);

  const collapseToPill = () => {
    setMode("pill");
    setDraft("");
  };

  const hideWindow = () => {
    invoke("hide_floating_bar").catch(() => {});
  };

  // Closing the dialog should dismiss the window entirely, matching the
  // Cmd+Enter toggle — reset state so the next activation starts fresh.
  const dismiss = () => {
    setMode("pill");
    setDraft("");
    hideWindow();
  };

  const handleSend = async () => {
    const text = draft.trim();
    if (!text || isStreaming) return;
    setDraft("");
    setMode("response");
    await sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      if (mode === "response") {
        dismiss();
      } else if (draft.length > 0) {
        setDraft("");
      } else {
        dismiss();
      }
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const lastUser = [...messages].reverse().find((m) => m.role === "user");

  if (!isSignedIn) {
    return (
      <div ref={rootRef} className="floating-root">
        <div className="floating-card floating-signin" onClick={hideWindow}>
          <span>Sign in to use Nooto</span>
        </div>
      </div>
    );
  }

  return (
    <div ref={rootRef} className="floating-root">
      {mode === "pill" && (
        <button
          type="button"
          className="floating-pill"
          aria-label="Open Ask Nooto"
          onClick={() => setMode("input")}
        />
      )}

      {mode === "alert" && alert && (
        <button
          type="button"
          className="floating-card floating-alert"
          onClick={() => {
            if (alertTimerRef.current != null) {
              window.clearTimeout(alertTimerRef.current);
              alertTimerRef.current = null;
            }
            setMode("pill");
            setAlert(null);
            hideWindow();
          }}
        >
          <div className="floating-alert-icon">
            <AlertTriangle size={16} />
          </div>
          <div className="floating-alert-text">
            <div className="floating-alert-title">{alert.title}</div>
            <div className="floating-alert-body">{alert.body}</div>
          </div>
        </button>
      )}

      {mode === "listening" && (
        <div className="floating-card floating-listening">
          <div className="live-listening-row">
            <div className="floating-mic">
              <Mic size={16} />
              <span className="floating-mic-dot" />
            </div>
            <div className="live-waveform" data-active="true">
              <Waveform barCount={10} height={18} />
            </div>
            <div className="floating-listening-text" style={{ flex: 1, minWidth: 0 }}>
              {liveTranscript || (
                <span className="floating-listening-hint">
                  Listening… release Option to send
                </span>
              )}
            </div>
            <AudioSourceSelector compact disabled />
          </div>
          {(liveSegments.length > 0 ||
            Object.values(livePartial).some((t) => t && t.trim())) && (
            <div
              style={{
                maxHeight: 220,
                overflowY: "auto",
                marginTop: 8,
              }}
            >
              <SpeakerBubbles
                segments={liveSegments}
                partialBySpeaker={livePartial}
                compact
                onSpeakerTapped={(segment) => {
                  const latest = [...liveSegments]
                    .reverse()
                    .find((s) => s.speaker === segment.speaker);
                  const partial = livePartial[segment.speaker];
                  setIdentifyingSpeaker({
                    speaker: segment.speaker,
                    speakerId: segment.speakerId,
                    sampleText: latest?.text || partial || segment.text,
                  });
                }}
              />
            </div>
          )}
          <LiveNameSpeakerSheet
            speaker={identifyingSpeaker}
            onClose={() => setIdentifyingSpeaker(null)}
          />
        </div>
      )}

      {mode === "input" && (
        <div className="floating-card floating-input">
          <textarea
            ref={textareaRef}
            className="floating-textarea"
            placeholder="Ask Nooto…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              if (!draft.trim() && !isStreaming) collapseToPill();
            }}
            rows={1}
          />
          <button
            type="button"
            className="floating-send"
            onClick={handleSend}
            disabled={!draft.trim() || isStreaming}
            aria-label="Send"
          >
            {isStreaming ? <Loader2 className="spin" size={16} /> : <ArrowUp size={16} />}
          </button>
        </div>
      )}

      {mode === "response" && (
        <div className="floating-card floating-response">
          <div className="floating-response-header">
            <span className="floating-response-query">{lastUser?.content ?? ""}</span>
            <button
              type="button"
              className="floating-close"
              onClick={dismiss}
              aria-label="Close conversation"
            >
              <X size={14} />
            </button>
          </div>
          <div className="floating-response-body">
            {lastAssistant?.content ? (
              <GenerativeMarkdown
                content={lastAssistant.content}
                isAnimating={lastAssistant.isStreaming}
              />
            ) : (
              <span className="floating-response-thinking">
                <Loader2 className="spin" size={14} /> Thinking…
              </span>
            )}
          </div>
          <div className="floating-response-footer">
            <textarea
              ref={textareaRef}
              className="floating-textarea followup"
              placeholder={isStreaming ? "Streaming…" : "Follow up…"}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
            />
            <button
              type="button"
              className="floating-send"
              onClick={handleSend}
              disabled={!draft.trim() || isStreaming}
              aria-label="Send"
            >
              {isStreaming ? <Loader2 className="spin" size={16} /> : <ArrowUp size={16} />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
