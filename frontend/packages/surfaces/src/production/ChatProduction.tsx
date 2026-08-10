import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type {
  ProductionChatStore,
  ChatMessage,
  ChatCapabilities,
  RetainedChatSend,
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

function isSafeStagedAttachment(attachment: StagedChatAttachment): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(attachment.id) &&
    /^[!#$%&'*+.^_`|~0-9A-Za-z-]+\/[!#$%&'*+.^_`|~0-9A-Za-z-]+$/u.test(attachment.mimeType) &&
    attachment.mimeType.length <= 127 &&
    Number.isSafeInteger(attachment.sizeBytes) &&
    attachment.sizeBytes > 0 &&
    attachment.expiresAt.length === 24 &&
    !Number.isNaN(Date.parse(attachment.expiresAt)) &&
    new Date(attachment.expiresAt).toISOString() === attachment.expiresAt &&
    attachment.state === "staged";
}

function isValidAttachmentSelection(
  capabilities: ChatCapabilities,
  attachments: readonly StagedChatAttachment[],
): boolean {
  if (attachments.length === 0) return true;
  if (
    capabilities.maxAttachmentsPerMessage === null ||
    capabilities.maxAttachmentBytes === null ||
    capabilities.allowedAttachmentMimeTypes === null ||
    attachments.length > capabilities.maxAttachmentsPerMessage
  ) return false;
  const maxAttachmentBytes = capabilities.maxAttachmentBytes;
  const allowedAttachmentMimeTypes = capabilities.allowedAttachmentMimeTypes;
  const ids = new Set<string>();
  return attachments.every((attachment) => {
    if (
      !isSafeStagedAttachment(attachment) ||
      ids.has(attachment.id) ||
      attachment.sizeBytes > maxAttachmentBytes ||
      !allowedAttachmentMimeTypes.includes(attachment.mimeType)
    ) return false;
    ids.add(attachment.id);
    return true;
  });
}

function sameAttachmentIds(
  current: readonly StagedChatAttachment[],
  submitted: readonly StagedChatAttachment[],
): boolean {
  return current.length === submitted.length &&
    current.every((attachment, index) => attachment.id === submitted[index]?.id);
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
  const [deadLetters, setDeadLetters] = useState<readonly RetainedChatSend[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [sending, setSending] = useState(false);
  const [staging, setStaging] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  const messageListRef = useRef<HTMLOListElement>(null);
  const sendInFlightRef = useRef(false);
  const stagingInFlightRef = useRef(false);
  const attachmentsRef = useRef<readonly StagedChatAttachment[]>(attachments);
  const capabilitiesRef = useRef(capabilities);
  attachmentsRef.current = attachments;
  capabilitiesRef.current = capabilities;
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
      const [page, retained] = await Promise.all([store.history(), store.deadLetters()]);
      setDeadLetters(retained);
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
  const selectionValid = isValidAttachmentSelection(capabilities, attachments);
  const canSend = draft.trim().length > 0 && selectionValid && !sending;

  const send = async (): Promise<void> => {
    if (sendInFlightRef.current) return;
    const text = draft.trim();
    if (!text) return;
    const submittedDraft = draft;
    const submittedAttachments = [...attachmentsRef.current];
    if (!isValidAttachmentSelection(capabilitiesRef.current, submittedAttachments)) {
      setOperationError(t(locale, "chat.error"));
      return;
    }
    sendInFlightRef.current = true;
    setSending(true);
    setOperationError(null);
    try {
      await store.send({
        text,
        attachmentIds: submittedAttachments.map((attachment) => attachment.id),
      });
      setDraft((current) => current === submittedDraft ? "" : current);
      setAttachments((current) => {
        const submittedIds = new Set(submittedAttachments.map((attachment) => attachment.id));
        const next = sameAttachmentIds(current, submittedAttachments)
          ? []
          : current.filter((attachment) => !submittedIds.has(attachment.id));
        attachmentsRef.current = next;
        return next;
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
    } finally {
      sendInFlightRef.current = false;
      setSending(false);
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
    if (
      !stagingAvailable ||
      !capState.enabled ||
      sendInFlightRef.current ||
      stagingInFlightRef.current
    ) return;
    stagingInFlightRef.current = true;
    setStaging(true);
    setOperationError(null);
    try {
      const staged = await store.stageAttachment();
      if (staged === null) return;
      const current = attachmentsRef.current;
      const candidate = [...current, staged];
      if (!isValidAttachmentSelection(capabilitiesRef.current, candidate)) {
        setOperationError(t(locale, "chat.error"));
        return;
      }
      attachmentsRef.current = candidate;
      setAttachments(candidate);
    } catch {
      setOperationError(t(locale, "chat.error"));
    } finally {
      stagingInFlightRef.current = false;
      setStaging(false);
    }
  };

  const removeAttachment = (id: string): void => {
    if (sendInFlightRef.current) return;
    setAttachments((current) => {
      const next = current.filter((item) => item.id !== id);
      attachmentsRef.current = next;
      return next;
    });
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
                    <p className="chat-message-text">
                      {message.text || (message.delivery.kind === "failed"
                        ? t(locale, "chat.responseUnavailable")
                        : "")}
                    </p>
                    {message.attachments.length > 0 && (
                      <ul className="chat-message-attachments" aria-label={t(locale, "chat.attachments")}>
                        {message.attachments.map((attachment) => (
                          <li key={attachment.id}>
                            <span className="chat-message-attachment-name">{attachment.displayName}</span>
                            <span>{t(locale, "chat.attachmentMetadata", {
                              mediaType: attachment.mediaType,
                              sizeBytes: attachment.sizeBytes,
                            })}</span>
                            {attachment.contentReference === null && (
                              <span>{t(locale, "chat.attachmentContentUnavailable")}</span>
                            )}
                          </li>
                        ))}
                      </ul>
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
        {deadLetters.length > 0 && (
          <section className="dead-letter-panel chat-dead-letters" aria-label={t(locale, "dead.title")}>
            <h2>{t(locale, "dead.title")}</h2>
            {deadLetters.map((letter) => (
              <div className="dead-letter" key={letter.opId}>
                <p>{t(locale, "dead.body")}</p>
                {letter.text !== null && (
                  <pre className="dead-letter-payload" aria-label={t(locale, "chat.composerLabel")}>
                    {letter.text}
                  </pre>
                )}
                {letter.attachmentIds !== null && letter.attachmentIds.length > 0 && (
                  <ol className="chat-dead-attachment-ids" aria-label={t(locale, "chat.attachments")}>
                    {letter.attachmentIds.map((id) => <li key={id}><code>{id}</code></li>)}
                  </ol>
                )}
                <button type="button" onClick={() => void run(() => store.discardDeadLetter(letter.opId))}>
                  {t(locale, "dead.remove")}
                </button>
              </div>
            ))}
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
                  <span>{t(locale, "chat.attachmentReady", {
                    mimeType: attachment.mimeType,
                    sizeBytes: attachment.sizeBytes,
                  })}</span>
                  <button type="button" disabled={sending} onClick={() => removeAttachment(attachment.id)} aria-label={t(locale, "chat.attachmentRemove")}>
                    {t(locale, "chat.attachmentRemove")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {attachmentHint && <p id="chat-attachment-hint" className="chat-attachment-hint">{attachmentHint}</p>}
          <div className="chat-composer-row">
            <button
              type="button"
              className="chat-attach"
              disabled={!stagingAvailable || !capState.enabled || sending || staging}
              aria-label={t(locale, "chat.attach")}
              aria-describedby={attachmentHint ? "chat-attachment-hint" : undefined}
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
