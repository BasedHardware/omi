import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type {
  ProductionChatStore,
  ChatMessage,
  ChatCapabilities,
  StagedChatAttachment,
} from "./ProductionChatStore.js";
import {
  attachmentCapState,
  mergeOlderPage,
  messageKey,
  reconcileMessages,
} from "./chat-reconcile.js";
import { refreshPhaseNoticeKey } from "./lifecycle-presentation.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge } from "./ProductionPrimitives.js";
import "./chat.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;

function phaseLabel(status: StoreStatus, locale: Locale): string | null {
  const key = refreshPhaseNoticeKey(status.refresh.phase);
  return key === null ? null : t(locale, key);
}

function roleLabel(role: ChatMessage["role"], locale: Locale): string {
  return role === "user" ? t(locale, "chat.roleUser") : t(locale, "chat.roleAssistant");
}

function deliveryLabel(message: ChatMessage, locale: Locale): string | null {
  if (message.delivery.kind === "streaming") return t(locale, "chat.streaming");
  if (
    message.delivery.kind === "canonical" &&
    message.delivery.generationOutcome === "cancelled"
  ) return t(locale, "chat.stopped");
  if (message.delivery.kind === "echo") return t(locale, "chat.pending");
  if (message.delivery.kind === "failed") return t(locale, "chat.failed");
  return null;
}

export function ChatProduction({ store, fixture, locale = "en", onReady }: {
  store: ProductionChatStore;
  fixture?: string;
  locale?: Locale;
  onReady?: () => void;
}): React.JSX.Element {
  const [messages, setMessages] = useState<readonly ChatMessage[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [olderCursor, setOlderCursor] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<ChatCapabilities>(() => store.capabilities());
  const [status, setStatus] = useState(store.status());
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<StagedChatAttachment[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  const messageListRef = useRef<HTMLOListElement>(null);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  // A chat opens on its newest message. Landing at the top of history means the reader
  // sees the oldest thing said and has to scroll to find the answer they just asked for.
  // Reads layout only — no timers, no wall clock.
  useEffect(() => {
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      const page = await store.history();
      setMessages((current) => {
        const next = reconcileMessages(current, page.messages);
        setHasOlder(page.hasOlder);
        setOlderCursor(page.olderCursor);
        setCapabilities(store.capabilities());
        return next;
      });
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
    }
    setStatus(store.status());
  }, [locale, store]);

  const run = useCallback<RunOperation>(async (operation) => {
    setOperationError(null);
    try {
      await operation();
      await reload();
      return true;
    } catch {
      setOperationError(t(locale, "chat.error"));
      setStatus(store.status());
      return false;
    }
  }, [locale, reload, store]);

  useEffect(() => {
    let active = true;
    const unsubscribe = store.subscribe(() => { if (active) void reload(); });
    const boot = async (): Promise<void> => {
      await reload();
      try {
        await store.refresh();
      } catch {
        setOperationError(t(locale, "lifecycle.error"));
        await reload();
      }
      await reload();
      if (active && !readyRef.current) {
        readyRef.current = true;
        onReadyRef.current?.();
      }
    };
    void boot();
    return () => { active = false; unsubscribe(); };
  }, [locale, reload, store]);

  const notice = phaseLabel(status, locale);
  const queueLabel = useMemo(() => {
    const count = status.queue.pendingCount;
    if (!count) return null;
    if (status.queue.phase === "needs-auth") return t(locale, "queue.paused");
    if (status.queue.phase === "retrying") return t(locale, "queue.retrying");
    if (status.queue.phase === "sending") return t(locale, "queue.sending", { count });
    return t(locale, "queue.queuedCount", { count });
  }, [locale, status]);

  const capState = attachmentCapState(capabilities, attachments.length);
  const stagingAvailable = store.stagingAvailable();
  const canSend = draft.trim().length > 0;

  const send = async (): Promise<void> => {
    const text = draft.trim();
    if (!text) return;
    const submittedAttachments = attachments;
    setDraft((current) => current.trim() === text ? "" : current);
    setAttachments([]);
    setOperationError(null);
    try {
      await store.send({
        text,
        attachmentIds: submittedAttachments.map((attachment) => attachment.id),
      });
      const page = await store.history();
      setMessages((current) => reconcileMessages(current, page.messages));
      setHasOlder(page.hasOlder);
      setOlderCursor(page.olderCursor);
      setCapabilities(store.capabilities());
      setStatus(store.status());
    } catch {
      setOperationError(t(locale, "chat.error"));
      setStatus(store.status());
    }
  };

  const loadOlder = async (): Promise<void> => {
    if (!olderCursor || loadingOlder) return;
    setLoadingOlder(true);
    setOperationError(null);
    try {
      const page = await store.loadOlder(olderCursor);
      setMessages((current) => mergeOlderPage(current, page));
      setHasOlder(page.hasOlder);
      setOlderCursor(page.olderCursor);
      setStatus(store.status());
    } catch {
      setOperationError(t(locale, "chat.error"));
      setStatus(store.status());
    } finally {
      setLoadingOlder(false);
    }
  };

  const attach = async (): Promise<void> => {
    if (!stagingAvailable || !capState.enabled) return;
    setOperationError(null);
    try {
      const staged = await store.stageAttachment();
      if (staged === null) return;
      if (
        capabilities.maxAttachmentBytes === null ||
        capabilities.allowedAttachmentMimeTypes === null ||
        staged.sizeBytes > capabilities.maxAttachmentBytes ||
        !capabilities.allowedAttachmentMimeTypes.includes(staged.mimeType)
      ) {
        setOperationError(t(locale, "chat.error"));
        return;
      }
      setAttachments((current) => [...current, staged]);
    } catch {
      setOperationError(t(locale, "chat.error"));
    }
  };

  const removeAttachment = (id: string): void => {
    setAttachments((current) => current.filter((item) => item.id !== id));
  };

  const retryFailed = (clientMessageId: string): void => {
    void run(() => store.retry(clientMessageId));
  };

  const cancelGeneration = (generationId: string): void => {
    void run(() => store.cancel(generationId));
  };

  const attachmentHint = !stagingAvailable
    ? t(locale, "chat.attachmentUnavailable")
    : capState.reason === "unknown-cap"
    ? t(locale, "chat.attachmentCapUnknown")
    : capState.reason === "at-limit" && capabilities.maxAttachmentsPerMessage !== null
      ? t(locale, "chat.attachmentLimitReached", { count: capabilities.maxAttachmentsPerMessage })
      : capabilities.maxAttachmentsPerMessage !== null
        ? t(locale, "chat.attachmentLimit", { count: capabilities.maxAttachmentsPerMessage })
        : null;

  return (
    <main className="production-shell" data-production-shell="true" data-route="chat" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"}>
      <ProductionChrome locale={locale} active="chat" placement="top" />
      <section className="desktop-page-panel">
        <header className="production-header chat-header">
          <div>
            <p className="eyebrow">{t(locale, "chat.title")}</p>
            <h1>{t(locale, "chat.title")}</h1>
            <p>{t(locale, "chat.subtitle")}</p>
          </div>
          <div className="header-actions">
            {status.refresh.phase !== "ready" && (
              <button type="button" onClick={() => void run(() => store.refresh())} aria-label={t(locale, "common.retry")}>
                {t(locale, "common.retry")}
              </button>
            )}
          </div>
        </header>
        {fixture && <ProductionDataSourceBadge source={{ kind: "fixture", fixture }} locale={locale} />}
        <div className="surface-notices" aria-live="polite">
          {notice && <div className={`status-notice ${status.refresh.phase}`} role="status">{notice}</div>}
          {queueLabel && <div className={`queue-notice ${status.queue.phase}`} role="status">{queueLabel}</div>}
          {operationError && <div className="operation-error" role="alert">{operationError}</div>}
        </div>
        {status.refresh.phase === "initial-loading" ? (
          <p className="chat-empty-state">{t(locale, "common.loading")}</p>
        ) : status.refresh.phase === "unavailable" && messages.length === 0 ? (
          <p className="chat-empty-state">{t(locale, "lifecycle.unavailable")}</p>
        ) : status.refresh.phase === "ready" && messages.length === 0 ? (
          <div className="chat-empty-state">
            <strong>{t(locale, "chat.emptyTitle")}</strong>
            <p>{t(locale, "chat.emptyBody")}</p>
          </div>
        ) : (
          <section className="chat-thread" aria-label={t(locale, "chat.messagesLabel")}>
            <div className="chat-history-controls">
              {hasOlder && olderCursor ? (
                <button type="button" onClick={() => void loadOlder()} disabled={loadingOlder} aria-label={loadingOlder ? t(locale, "chat.loadingOlder") : t(locale, "chat.loadOlder")}>
                  {loadingOlder ? t(locale, "chat.loadingOlder") : t(locale, "chat.loadOlder")}
                </button>
              ) : (
                <p className="chat-history-start">{t(locale, "chat.historyStart")}</p>
              )}
            </div>
            <ol className="chat-message-list" ref={messageListRef}>
              {messages.map((message) => {
                const statusLabel = deliveryLabel(message, locale);
                const busy = message.delivery.kind === "streaming";
                const failedClientMessageId = message.delivery.kind === "failed" && message.delivery.retryable
                  ? message.delivery.clientMessageId
                  : null;
                const streamingGenerationId = message.delivery.kind === "streaming"
                  ? message.delivery.generationId
                  : null;
                const cancelled = message.delivery.kind === "canonical" &&
                  message.delivery.generationOutcome === "cancelled";
                return (
                  <li
                    key={messageKey(message)}
                    className={`chat-message is-${message.role}${message.delivery.kind === "failed" ? " is-failed" : ""}${message.delivery.kind === "echo" ? " is-pending" : ""}${busy ? " is-streaming" : ""}${cancelled ? " is-cancelled" : ""}`}
                    data-delivery={message.delivery.kind}
                    aria-busy={busy || undefined}
                  >
                    <div className="chat-message-meta">
                      <span className="chat-role">{roleLabel(message.role, locale)}</span>
                      {statusLabel && <span className="chat-delivery-label">{statusLabel}</span>}
                    </div>
                    <p className="chat-message-text">{message.text}</p>
                    {failedClientMessageId && (
                      <button type="button" onClick={() => retryFailed(failedClientMessageId)} aria-label={t(locale, "chat.retrySend")}>
                        {t(locale, "chat.retrySend")}
                      </button>
                    )}
                    {streamingGenerationId && (
                      <button type="button" onClick={() => cancelGeneration(streamingGenerationId)} aria-label={t(locale, "chat.stop")}>
                        {t(locale, "chat.stop")}
                      </button>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        )}
        <form
          className="chat-composer"
          aria-label={t(locale, "chat.composerLabel")}
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          {attachments.length > 0 && (
            <ul className="chat-attachments" aria-label={t(locale, "chat.attachments")}>
              {attachments.map((attachment) => (
                <li key={attachment.id}>
                  <span>{attachment.displayName}</span>
                  <button type="button" onClick={() => removeAttachment(attachment.id)} aria-label={t(locale, "chat.attachmentRemove")}>
                    {t(locale, "chat.attachmentRemove")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {attachmentHint && <p className="chat-attachment-hint">{attachmentHint}</p>}
          <div className="chat-composer-row">
            <button
              type="button"
              className="chat-attach"
              disabled={!stagingAvailable || !capState.enabled}
              aria-label={t(locale, "chat.attach")}
              title={attachmentHint ?? t(locale, "chat.attach")}
              onClick={() => void attach()}
            >
              {t(locale, "chat.attach")}
            </button>
            <textarea
              className="chat-draft"
              value={draft}
              placeholder={t(locale, "chat.composerPlaceholder")}
              aria-label={t(locale, "chat.composerLabel")}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button type="submit" className="chat-send" disabled={!canSend} aria-label={t(locale, "chat.send")}>
              {t(locale, "chat.send")}
            </button>
          </div>
        </form>
      </section>
      <ProductionChrome locale={locale} active="chat" placement="bottom" />
    </main>
  );
}
