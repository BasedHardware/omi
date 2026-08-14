import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type {
  ProductionChatStore,
  ChatMessage,
  ChatCapabilities,
  RetainedChatSend,
  StagedChatAttachment,
} from "./ProductionChatStore.js";
import {
  asScanTerminal,
  attachmentsAreAdmissibleForSend,
  canRemoveTrayAttachment,
  canRetryAttachmentScan,
  scanMetadataFromWire,
  toTrayAttachment,
  type ChatTrayAttachment,
} from "./chat-attachment-scan.js";
import {
  attachmentCapState,
  mergeOlderPage,
  messageKey,
  reconcileMessages,
} from "./chat-reconcile.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionPageHeader, type ProductionAnnouncementScheduler } from "./ProductionPrimitives.js";
import "./chat.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
type ChatScrollAnchor = { readonly scrollHeight: number; readonly scrollTop: number };

const CHAT_LIVE_EDGE_PX = 24;

function chatScrollTarget(list: HTMLOListElement): HTMLElement {
  if (list.ownerDocument.documentElement.dataset["platform"] === "mobile") {
    return list.ownerDocument.scrollingElement as HTMLElement | null ?? list;
  }
  return list;
}

function isAtChatLiveEdge(target: HTMLElement): boolean {
  return target.scrollHeight - target.scrollTop - target.clientHeight <= CHAT_LIVE_EDGE_PX;
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

function chatAnnouncement(messages: readonly ChatMessage[], locale: Locale): string | null {
  const latest = [...messages].reverse()[0];
  if (!latest) return null;
  const agentUpdate = latest.agentRun?.events.at(-1)?.safeSummary;
  if (agentUpdate) return agentUpdate;
  if (latest.delivery.kind === "streaming") return t(locale, "chat.streaming");
  if (latest.delivery.kind === "echo") return t(locale, "chat.pending");
  if (latest.delivery.kind === "failed") return t(locale, "chat.failed");
  if (latest.delivery.kind === "canonical") {
    if (latest.delivery.generationOutcome === "cancelled") return t(locale, "chat.stopped");
    if (latest.role === "assistant" && latest.delivery.generationOutcome === "completed") return t(locale, "chat.completed");
  }
  return t(locale, "lifecycle.resultsCount", { count: messages.length });
}

function agentRunStateLabel(state: NonNullable<ChatMessage["agentRun"]>["state"], locale: Locale): string {
  if (state === "complete") return t(locale, "chat.agentRunComplete");
  if (state === "failed") return t(locale, "chat.agentRunFailed");
  return t(locale, "chat.agentRunObserving");
}

function agentCapabilityLabel(message: ChatMessage, locale: Locale): string {
  const capability = [...(message.agentRun?.events ?? [])].reverse()
    .find((event) => event.kind === "capability_receipt");
  if (capability?.kind !== "capability_receipt") return t(locale, "chat.agentUnknown");
  if (capability.details.tier === "deterministic-scripted") return t(locale, "chat.agentScripted");
  if (capability.details.tier === "real-provider") return t(locale, "chat.agentProvider");
  if (
    capability.details.adapter === "omi-llm-gateway" ||
    capability.details.adapter === "omi-llm-gateway-injected-transport"
  ) {
    return t(locale, "chat.agentLocalTestGateway");
  }
  return t(locale, "chat.agentUnknown");
}

function approvalIsPending(
  events: NonNullable<ChatMessage["agentRun"]>["events"],
  event: NonNullable<ChatMessage["agentRun"]>["events"][number],
): boolean {
  if (event.kind !== "approval_requested") return false;
  return !events.some((candidate) =>
    candidate.kind === "approval_resolved" && candidate.sequence > event.sequence
  );
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
  current: readonly ChatTrayAttachment[],
  submitted: readonly ChatTrayAttachment[],
): boolean {
  return current.length === submitted.length &&
    current.every((attachment, index) => attachment.id === submitted[index]?.id);
}

function attachmentScanLabel(state: ChatTrayAttachment["scanState"], locale: Locale): string {
  if (state === "staged") return t(locale, "chat.attachmentAwaitingCheck");
  if (state === "scanning") return t(locale, "chat.attachmentScanning");
  if (state === "clean") return t(locale, "chat.attachmentClean");
  if (state === "rejected") return t(locale, "chat.attachmentRejected");
  if (state === "timed_out") return t(locale, "chat.attachmentTimedOut");
  if (state === "error") return t(locale, "chat.attachmentScanError");
  return t(locale, "chat.attachmentBound");
}

export function ChatProduction({ store, fixture, locale = "en", onReady, announcementScheduler }: {
  store: ProductionChatStore;
  fixture?: string;
  locale?: Locale;
  onReady?: () => void;
  announcementScheduler?: ProductionAnnouncementScheduler;
}): React.JSX.Element {
  const [messages, setMessages] = useState<readonly ChatMessage[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [olderCursor, setOlderCursor] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<ChatCapabilities>(() => store.capabilities());
  const [status, setStatus] = useState(store.status());
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<ChatTrayAttachment[]>([]);
  const [deadLetters, setDeadLetters] = useState<readonly RetainedChatSend[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [sending, setSending] = useState(false);
  const [staging, setStaging] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [showLatest, setShowLatest] = useState(false);
  const [composerBlockSize, setComposerBlockSize] = useState(0);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  const messageListRef = useRef<HTMLOListElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const historyRequestRef = useRef(0);
  const sendInFlightRef = useRef(false);
  const stagingInFlightRef = useRef(false);
  const followingLatestRef = useRef(true);
  const olderAnchorRef = useRef<ChatScrollAnchor | null>(null);
  const previousMessagesRef = useRef<readonly ChatMessage[]>([]);
  const touchYRef = useRef<number | null>(null);
  const attachmentsRef = useRef<readonly ChatTrayAttachment[]>(attachments);
  const scanEpochRef = useRef(new Map<string, number>());
  const capabilitiesRef = useRef(capabilities);
  attachmentsRef.current = attachments;
  capabilitiesRef.current = capabilities;
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const jumpToLatest = useCallback((): void => {
    const list = messageListRef.current;
    if (!list) return;
    const target = chatScrollTarget(list);
    target.scrollTop = target.scrollHeight;
    followingLatestRef.current = true;
    setShowLatest(false);
  }, []);

  const leaveLiveEdge = useCallback((): void => {
    followingLatestRef.current = false;
    setShowLatest(true);
  }, []);

  const updateFollowingFromTarget = useCallback((target: HTMLElement): void => {
    const atEdge = isAtChatLiveEdge(target);
    followingLatestRef.current = atEdge;
    setShowLatest(!atEdge);
  }, []);

  // Follow growing output only while the reader remains at the live edge. Loading an
  // older page instead restores the exact visual anchor so prepended rows do not jump.
  useLayoutEffect(() => {
    const list = messageListRef.current;
    if (!list) return;
    const target = chatScrollTarget(list);
    const olderAnchor = olderAnchorRef.current;
    if (olderAnchor) {
      target.scrollTop = olderAnchor.scrollTop + target.scrollHeight - olderAnchor.scrollHeight;
      olderAnchorRef.current = null;
      followingLatestRef.current = false;
      setShowLatest(true);
    } else if (followingLatestRef.current) {
      target.scrollTop = target.scrollHeight;
      setShowLatest(false);
    } else if (previousMessagesRef.current !== messages) {
      setShowLatest(true);
    }
    previousMessagesRef.current = messages;
  }, [messages]);

  // Streaming content can grow without changing the message array (fonts, wrapping,
  // attachments). ResizeObserver keeps that growth pinned only for an opted-in reader.
  useEffect(() => {
    const list = messageListRef.current;
    const ResizeObserverConstructor = list?.ownerDocument.defaultView?.ResizeObserver;
    if (!list || !ResizeObserverConstructor) return;
    const observer = new ResizeObserverConstructor(() => {
      if (followingLatestRef.current) jumpToLatest();
    });
    observer.observe(list);
    for (const message of list.children) observer.observe(message);
    return () => observer.disconnect();
  }, [jumpToLatest, messages.length]);

  // Mobile Chat uses the document scroller rather than a nested message scroller.
  // Listening there preserves scrollbar/accessibility-scroll behavior in addition to
  // the explicit wheel, touch, and keyboard intent handlers on the message list.
  useEffect(() => {
    const list = messageListRef.current;
    if (!list) return;
    const target = chatScrollTarget(list);
    if (target === list) return;
    const update = (): void => updateFollowingFromTarget(target);
    target.addEventListener("scroll", update, { passive: true });
    return () => target.removeEventListener("scroll", update);
  }, [messages.length, updateFollowingFromTarget]);

  // Mobile scrolls the document, so the Latest control must be viewport-fixed rather
  // than anchored to the end of a potentially very tall thread. Measure the sticky
  // composer so the control remains reachable without covering its actions.
  useLayoutEffect(() => {
    const composer = composerRef.current;
    const view = composer?.ownerDocument.defaultView;
    if (!composer || !view) return;
    const update = (): void => {
      const next = Math.ceil(composer.getBoundingClientRect().height);
      setComposerBlockSize((current) => current === next ? current : next);
    };
    update();
    view.addEventListener("resize", update);
    const ResizeObserverConstructor = view.ResizeObserver;
    const observer = ResizeObserverConstructor ? new ResizeObserverConstructor(update) : null;
    observer?.observe(composer);
    return () => {
      observer?.disconnect();
      view.removeEventListener("resize", update);
    };
  }, []);

  const reload = useCallback(async (): Promise<void> => {
    const request = ++historyRequestRef.current;
    try {
      const [page, retained] = await Promise.all([store.history(), store.deadLetters()]);
      if (request !== historyRequestRef.current) return;
      setDeadLetters(retained);
      setMessages((current) => reconcileMessages(current, page.messages));
      setHasOlder(page.hasOlder);
      setOlderCursor(page.olderCursor);
      setCapabilities(store.capabilities());
    } catch {
      if (request !== historyRequestRef.current) return;
      setOperationError(t(locale, "lifecycle.error"));
    }
    if (request === historyRequestRef.current) setStatus(store.status());
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

  const capState = attachmentCapState(capabilities, attachments.length);
  const stagingAvailable = store.stagingAvailable();
  const selectionValid = isValidAttachmentSelection(capabilities, attachments);
  const scanAdmissible = attachmentsAreAdmissibleForSend(attachments);
  const canSend = draft.trim().length > 0 && selectionValid && scanAdmissible && !sending;

  const send = async (): Promise<void> => {
    if (sendInFlightRef.current) return;
    const text = draft.trim();
    if (!text) return;
    const submittedDraft = draft;
    const submittedAttachments = [...attachmentsRef.current];
    if (
      !isValidAttachmentSelection(capabilitiesRef.current, submittedAttachments) ||
      !attachmentsAreAdmissibleForSend(submittedAttachments)
    ) {
      setOperationError(t(locale, "chat.error"));
      return;
    }
    sendInFlightRef.current = true;
    followingLatestRef.current = true;
    setShowLatest(false);
    setSending(true);
    setOperationError(null);
    let postSendHistoryRequest: number | null = null;
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
      const request = ++historyRequestRef.current;
      postSendHistoryRequest = request;
      const page = await store.history();
      if (request === historyRequestRef.current) {
        setMessages((current) => reconcileMessages(current, page.messages));
        setHasOlder(page.hasOlder);
        setOlderCursor(page.olderCursor);
        setCapabilities(store.capabilities());
        setStatus(store.status());
      }
    } catch {
      if (
        postSendHistoryRequest !== null &&
        postSendHistoryRequest !== historyRequestRef.current
      ) return;
      setOperationError(t(locale, "chat.error"));
      setStatus(store.status());
    } finally {
      sendInFlightRef.current = false;
      setSending(false);
    }
  };

  const loadOlder = async (): Promise<void> => {
    if (!olderCursor || loadingOlder) return;
    const list = messageListRef.current;
    if (list) {
      const target = chatScrollTarget(list);
      olderAnchorRef.current = { scrollHeight: target.scrollHeight, scrollTop: target.scrollTop };
      followingLatestRef.current = false;
    }
    setLoadingOlder(true);
    setOperationError(null);
    try {
      const page = await store.loadOlder(olderCursor);
      setMessages((current) => mergeOlderPage(current, page));
      setHasOlder(page.hasOlder);
      setOlderCursor(page.olderCursor);
      setStatus(store.status());
    } catch {
      olderAnchorRef.current = null;
      setOperationError(t(locale, "chat.error"));
      setStatus(store.status());
    } finally {
      setLoadingOlder(false);
    }
  };

  const bumpScanEpoch = (id: string): number => {
    const next = (scanEpochRef.current.get(id) ?? 0) + 1;
    scanEpochRef.current.set(id, next);
    return next;
  };

  const runScan = async (id: string): Promise<void> => {
    const epoch = bumpScanEpoch(id);
    const current = attachmentsRef.current.find((attachment) => attachment.id === id);
    if (!current) return;
    const scanning = attachmentsRef.current.map((attachment) =>
      attachment.id === id ? { ...attachment, scanState: "scanning" as const } : attachment,
    );
    attachmentsRef.current = scanning;
    setAttachments(scanning);
    let terminal = null as ReturnType<typeof asScanTerminal>;
    try {
      terminal = asScanTerminal(await store.scanAttachment(current));
    } catch {
      terminal = "error";
    }
    if (scanEpochRef.current.get(id) !== epoch) return;
    const result = terminal ?? "error";
    setAttachments((existing) => {
      const updated = existing.map((attachment) =>
        attachment.id === id ? { ...attachment, scanState: result } : attachment,
      );
      attachmentsRef.current = updated;
      return updated;
    });
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
      const candidateHost = [...current, staged];
      if (!isValidAttachmentSelection(capabilitiesRef.current, candidateHost)) {
        setOperationError(t(locale, "chat.error"));
        return;
      }
      const wire = scanMetadataFromWire(staged);
      const initialScan = wire.scanState ?? "scanning";
      const candidate = [...current, toTrayAttachment(staged, initialScan, wire.scannerId)];
      attachmentsRef.current = candidate;
      setAttachments(candidate);
      if (asScanTerminal(initialScan) === null && initialScan !== "bound") {
        await runScan(staged.id);
      }
    } catch {
      setOperationError(t(locale, "chat.error"));
    } finally {
      stagingInFlightRef.current = false;
      setStaging(false);
    }
  };

  const retryAttachmentScan = (id: string): void => {
    if (sendInFlightRef.current) return;
    const target = attachmentsRef.current.find((attachment) => attachment.id === id);
    if (!target || !canRetryAttachmentScan(target.scanState)) return;
    void runScan(id);
  };

  const removeAttachment = (id: string): void => {
    if (sendInFlightRef.current) return;
    const target = attachmentsRef.current.find((attachment) => attachment.id === id);
    if (!target || !canRemoveTrayAttachment(target.scanState)) return;
    bumpScanEpoch(id);
    setAttachments((current) => {
      const next = current.filter((item) => item.id !== id);
      attachmentsRef.current = next;
      return next;
    });
  };

  const cancelGeneration = (generationId: string): void => {
    void run(() => store.cancel(generationId));
  };

  const resolveApproval = (resolution: "approved" | "denied" | "cancelled"): void => {
    void run(() => store.resolveApproval(resolution));
  };

  const startNewMessage = (failed: Extract<ChatMessage["delivery"], { kind: "failed" }>): void => {
    const original = messages.find((message) =>
      message.role === "user" &&
      message.delivery.kind === "canonical" &&
      message.delivery.clientMessageId === failed.clientMessageId
    );
    if (!original || draft.length > 0 || attachments.length > 0) {
      draftRef.current?.focus();
      return;
    }
    setDraft(original.text);
    draftRef.current?.focus();
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
  const admittedUserMessages = messages.filter(
    (message) => message.role === "user" && message.delivery.kind === "canonical",
  ).length;

  return (
    <main className="production-shell" aria-label={t(locale, "chat.title")} data-production-shell="true" data-route="chat" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"} data-consumer-chat-admission-count={admittedUserMessages} data-consumer-semantic={`chat:messages:${messages.length}:admitted:${admittedUserMessages}:streaming:${messages.some((message) => message.delivery.kind === "streaming") ? 1 : 0}:staging:${stagingAvailable ? 1 : 0}`}>
      <ProductionChrome locale={locale} active="chat" placement="top" commandHandlers={{
        "send-chat": send,
      }} commandEnabled={{ "send-chat": canSend }} />
      <section className="desktop-page-panel">
        <ProductionPageHeader className="production-header chat-header" eyebrow={t(locale, "chat.title")} title={t(locale, "chat.title")} description={t(locale, "chat.subtitle")} />
        <ProductionDataSourceBadge source={fixture ? { kind: "fixture", fixture } : { kind: "live", origin: "bridge" }} locale={locale} />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={status.refresh.phase}
          hasSavedData={status.refresh.hasSavedData}
          locale={locale}
          queue={status.queue}
          deadLetterCount={deadLetters.length}
          operationError={operationError}
          nextAction={status.refresh.phase !== "ready" ? t(locale, "common.retry") : null}
          retry={status.refresh.phase !== "ready" ? { onRetry: async () => { await run(() => store.refresh()); } } : null}
        />
        <ProductionLiveAnnouncement
          message={operationError ? null : chatAnnouncement(messages, locale)}
          {...(announcementScheduler ? { scheduler: announcementScheduler } : {})}
        />
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
            <ol
              className="chat-message-list"
              ref={messageListRef}
              tabIndex={0}
              onScroll={(event) => {
                updateFollowingFromTarget(chatScrollTarget(event.currentTarget));
              }}
              onWheel={(event) => { if (event.deltaY < 0) leaveLiveEdge(); }}
              onTouchStart={(event) => { touchYRef.current = event.touches[0]?.clientY ?? null; }}
              onTouchMove={(event) => {
                const nextY = event.touches[0]?.clientY ?? null;
                if (nextY !== null && touchYRef.current !== null && nextY > touchYRef.current) leaveLiveEdge();
                touchYRef.current = nextY;
              }}
              onKeyDown={(event) => {
                if (["ArrowUp", "PageUp", "Home"].includes(event.key)) leaveLiveEdge();
              }}
            >
              {messages.map((message) => {
                const statusLabel = deliveryLabel(message, locale);
                const busy = message.delivery.kind === "streaming";
                const streamingGenerationId = message.delivery.kind === "streaming"
                  ? message.delivery.generationId
                  : null;
                const cancelled = message.delivery.kind === "canonical" &&
                  message.delivery.generationOutcome === "cancelled";
                const failedDelivery = message.delivery.kind === "failed" ? message.delivery : null;
                const hasRecoverySource = failedDelivery !== null && messages.some((candidate) =>
                  candidate.role === "user" &&
                  candidate.delivery.kind === "canonical" &&
                  candidate.delivery.clientMessageId === failedDelivery.clientMessageId
                );
                // Capture once: `message.agentRun` is optional, and TS does not
                // keep the JSX guard inside the events `.map` closure.
                const agentRun = message.agentRun;
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
                    {failedDelivery?.source === "transport" && (
                      <div className="chat-failure-recovery" data-recovery="unsupported-stream">
                        <p>{t(locale, "chat.liveUpdatesUnavailable")}</p>
                        <p>{t(locale, "chat.liveUpdatesUnavailableHint")}</p>
                      </div>
                    )}
                    {message.role === "assistant" && agentRun && agentRun.events.length > 0 && (
                      <details className="chat-agent-run" data-agent-run-state={agentRun.state}>
                        <summary>
                          <span>{t(locale, "chat.agentRunDetails")}</span>
                          <span className="chat-agent-capability">{agentCapabilityLabel(message, locale)}</span>
                          <span className="chat-agent-state">{agentRunStateLabel(agentRun.state, locale)}</span>
                        </summary>
                        <ol aria-label={t(locale, "chat.agentRunLabel")}>
                          {agentRun.events.map((event) => (
                            <li key={`${event.sequence}:${event.kind}`} data-agent-event={event.kind}>
                              <p>{event.safeSummary}</p>
                              {event.kind === "context_receipt" && (
                                <p className="chat-agent-detail">
                                  <span>{t(locale, "chat.agentContext", { preview: event.details.redactedPreview })}</span>
                                  <span>{t(locale, "chat.agentContextReason", { reason: event.details.inclusionReason })}</span>
                                </p>
                              )}
                              {(event.kind === "tool_request" || event.kind === "tool_result" || event.kind === "tool_error") && (
                                <p className="chat-agent-detail">{t(locale, "chat.agentTool", { name: event.details.toolName })}</p>
                              )}
                              {event.kind === "approval_requested" && approvalIsPending(agentRun.events, event) && (
                                <div className="chat-agent-approval" data-approval-pending="true">
                                  <p className="chat-agent-detail">{event.details.reason}</p>
                                  <button type="button" data-approval-action="approved" onClick={() => resolveApproval("approved")}>
                                    {t(locale, "chat.agentApprovalAllow")}
                                  </button>
                                  <button type="button" data-approval-action="denied" onClick={() => resolveApproval("denied")}>
                                    {t(locale, "chat.agentApprovalDeny")}
                                  </button>
                                  <button type="button" data-approval-action="cancelled" onClick={() => resolveApproval("cancelled")}>
                                    {t(locale, "common.cancel")}
                                  </button>
                                </div>
                              )}
                              {event.kind === "usage" && (
                                <p className="chat-agent-detail">{t(locale, "chat.agentUsage", { count: event.details.totalTokens })}</p>
                              )}
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
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
                    {failedDelivery?.source === "provider" &&
                      failedDelivery.retryable && hasRecoverySource && (
                        <div className="chat-failure-recovery">
                          <button type="button" onClick={() => startNewMessage(failedDelivery)}>
                            {t(locale, "chat.startNewMessage")}
                          </button>
                          <p>{t(locale, "chat.startNewMessageHint")}</p>
                        </div>
                      )}
                  </li>
                );
              })}
            </ol>
            {showLatest && (
              <button
                type="button"
                className="chat-jump-latest"
                style={{ "--chat-mobile-composer-height": `${composerBlockSize}px` } as React.CSSProperties}
                onClick={jumpToLatest}
              >
                {t(locale, "chat.latest")}
              </button>
            )}
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
                {letter.attachmentCount !== null && letter.attachmentCount > 0 && (
                  <p className="chat-dead-attachment-summary">
                    {t(locale, "chat.retainedAttachmentCount", { count: letter.attachmentCount })}
                  </p>
                )}
                <button type="button" onClick={() => void run(() => store.discardDeadLetter(letter.opId))}>
                  {t(locale, "dead.remove")}
                </button>
              </div>
            ))}
          </section>
        )}
        <form
          ref={composerRef}
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
                <li
                  key={attachment.id}
                  data-attachment-scan={attachment.scanState}
                  data-attachment-scanner={attachment.scannerId}
                >
                  <span className="chat-attachment-meta">{t(locale, "chat.attachmentReady", {
                    mimeType: attachment.mimeType,
                    sizeBytes: attachment.sizeBytes,
                  })}</span>
                  <span className="chat-attachment-scan">{attachmentScanLabel(attachment.scanState, locale)}</span>
                  <span className="chat-attachment-scanner">{attachment.scannerId}</span>
                  {canRetryAttachmentScan(attachment.scanState) && (
                    <button
                      type="button"
                      data-attachment-scan-retry="true"
                      disabled={sending}
                      onClick={() => retryAttachmentScan(attachment.id)}
                      aria-label={t(locale, "chat.attachmentScanRetry")}
                    >
                      {t(locale, "common.retry")}
                    </button>
                  )}
                  {canRemoveTrayAttachment(attachment.scanState) && (
                    <button type="button" disabled={sending} onClick={() => removeAttachment(attachment.id)} aria-label={t(locale, "chat.attachmentRemove")}>
                      {t(locale, "chat.attachmentRemove")}
                    </button>
                  )}
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
              ref={draftRef}
              className="chat-draft"
              value={draft}
              placeholder={t(locale, "chat.composerPlaceholder")}
              aria-label={t(locale, "chat.composerLabel")}
              onChange={(event) => setDraft(event.target.value)}
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
