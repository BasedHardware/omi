import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { AlertTriangle, X } from "lucide-react";
import "./NotificationBar.css";

interface NotificationPayload {
  title: string;
  body: string;
  /** Auto-hide delay override in ms. Defaults to 6000. */
  autoHideMs?: number;
}

const DEFAULT_AUTO_HIDE_MS = 6000;
const POLL_INTERVAL_MS = 250;

export function NotificationBar() {
  const [payload, setPayload] = useState<NotificationPayload | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const applyPayload = (p: NotificationPayload) => {
      setPayload(p);
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      const delay = p.autoHideMs ?? DEFAULT_AUTO_HIDE_MS;
      timerRef.current = window.setTimeout(() => {
        setPayload(null);
        invoke("hide_notification_bar").catch(() => {});
        timerRef.current = null;
      }, delay);
    };

    const tick = async () => {
      if (cancelled) return;
      try {
        const pending = await invoke<NotificationPayload | null>(
          "notifications_poll",
        );
        if (cancelled) return;
        if (pending) applyPayload(pending);
      } catch {
        // Poll errors are non-fatal — the next tick will retry.
      }
      if (!cancelled) {
        window.setTimeout(tick, POLL_INTERVAL_MS);
      }
    };

    tick();

    return () => {
      cancelled = true;
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    let frame = 0;
    const push = () => {
      frame = 0;
      const height = Math.ceil(el.getBoundingClientRect().height);
      if (height > 0) {
        invoke("resize_notification_bar", { height }).catch(() => {});
      }
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
  }, [payload]);

  const dismiss = () => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setPayload(null);
    invoke("hide_notification_bar").catch(() => {});
  };

  if (!payload) {
    return <div ref={rootRef} className="notif-root" />;
  }

  return (
    <div ref={rootRef} className="notif-root">
      <div className="notif-card" role="alert">
        <div className="notif-icon">
          <AlertTriangle size={16} />
        </div>
        <div className="notif-text">
          <div className="notif-title">{payload.title}</div>
          <div className="notif-body">{payload.body}</div>
        </div>
        <button
          type="button"
          className="notif-close"
          onClick={dismiss}
          aria-label="Dismiss notification"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
