// Development-only component review. This does not mount the authenticated
// orchestrator or persist setup. Vite's production entry remains index.html.
import React, { useEffect, useRef, useState } from "react";
import { AppRegistry, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { DesktopOnboarding } from "../../react-native/src/desktop/DesktopOnboarding";
import { DesktopApp } from "../../react-native/src/desktop/DesktopApp";
import { Onboarding } from "../../react-native/src/ui/Onboarding";
import { ConversationsPage } from "../../react-native/src/pages/Conversations";
import { SettingsPage } from "../../react-native/src/pages/Settings";
import { ConnectorsPage } from "../../react-native/src/pages/Connectors";
import { MobileChat } from "../../react-native/src/mobile/MobileChat";
import {
  MobileOmnibar,
  type MobileOmnibarMode,
} from "../../react-native/src/mobile/MobileOmnibar";
import { LiveVoiceButton } from "../../react-native/src/ui/LiveVoiceButton";
import {
  DeviceSession,
  homeConnectionStatus,
} from "../../react-native/src/app/DeviceSession";
import type { PlatformNativeSnapshot } from "../../react-native/src/omiNative";
import type { ChatMessage } from "../../react-native/src/chatClient";
import { omiBackend } from "../../react-native/src/omiNative.web";
import type {
  DesktopReadOutcomes,
  DesktopReadProjection,
  ReadPageState,
  TaskProjection,
} from "../../react-native/src/desktopReadClient";
import {
  MobileAppSurface,
  type MobileRoute,
} from "../../react-native/src/mobile/MobileAppSurface";
import "./root.css";

const h = React.createElement;
const noop = () => undefined;
const surface = new URLSearchParams(location.search).get("surface") ?? "setup";
const example = new URLSearchParams(location.search).get("data");
const chatState = new URLSearchParams(location.search).get("chat");
const deviceState = new URLSearchParams(location.search).get("device");
const conversationState = new URLSearchParams(location.search).get(
  "conversations"
);
const previewDevice: PlatformNativeSnapshot = {
  bluetooth: "poweredOn",
  phase:
    deviceState === "connecting"
      ? "connecting"
      : deviceState === "error"
      ? "disconnected"
      : "connected",
  connectedDeviceId: deviceState === "error" ? null : "example-omi",
  devices: [
    {
      id: "example-omi",
      name: "Example Omi",
      connected: deviceState !== "connecting" && deviceState !== "error",
      battery: 73,
      information: { model: "Example device", firmware: "1.2.3" },
    },
  ],
  capture:
    deviceState === "waiting" || deviceState === "listening"
      ? "recording"
      : "idle",
  audioStatus:
    deviceState === "waiting"
      ? "waiting"
      : deviceState === "listening"
      ? "active"
      : undefined,
  lastEvent: "",
  microphone: "unknown",
  notifications: "unknown",
};
const page: ReadPageState = {
  windowStatus: "complete",
  complete: true,
  hasMore: false,
  nextCursor: null,
  completenessStatus: "complete",
  reasons: [],
};
const exampleNow = Date.now();
const exampleToday = (hour: number, minute: number) => {
  const date = new Date(exampleNow);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
};
const exampleYesterday = (hour: number, minute: number) => {
  const date = new Date(exampleNow);
  date.setDate(date.getDate() - 1);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
};

// Explicitly labelled, local-only fixtures for populated/empty layout review.
const exampleOutcomes: DesktopReadOutcomes = {
  conversations: {
    status: "success",
    value: {
      items:
        example === "empty"
          ? []
          : [
              {
                title: "Product standup",
                summary: "Q3 goals, hiring, and the next release.",
                startedAt: exampleToday(10, 24),
                finishedAt: exampleToday(10, 48),
              },
              {
                title: "Chat with Alex",
                summary: "Aligned on GTM and the quieter workspace plan.",
                startedAt: exampleToday(8, 41),
                finishedAt: exampleToday(9, 5),
              },
              {
                title: "1:1 with Taylor",
                summary: "Career growth, next steps, and time to think.",
                startedAt: exampleYesterday(16, 36),
                finishedAt: exampleYesterday(17, 2),
                starred: true,
              },
            ].map((item, index) => ({
              kind: "conversation" as const,
              id: `preview-conversation-${index}`,
              title: item.title,
              summary: item.summary,
              searchableText: `${item.title} ${item.summary}`,
              createdAt: item.startedAt,
              updatedAt: item.finishedAt,
              startedAt: item.startedAt,
              finishedAt: item.finishedAt,
              starred: "starred" in item ? item.starred === true : false,
              status: "completed",
              source: "desktop",
              visibility: "private" as const,
              folderId: null,
              locked: false,
              discarded: false,
            })),
      page,
    },
  },
  memories: {
    status: "success",
    value: {
      items:
        example === "empty"
          ? []
          : [
              {
                kind: "memory" as const,
                id: "preview-memory-1",
                title: "The launch review is Friday afternoon.",
                summary: "The launch review is Friday afternoon.",
                searchableText: "launch review Friday afternoon",
                citations: ["preview-conversation-0"],
                timestamp: Math.floor(Date.parse(exampleToday(11, 2)) / 1000),
                provenance: {
                  label: "conversation",
                  synthesisVersion: "preview",
                  inputDigest: null,
                  outputDigest: null,
                },
              },
            ],
      page,
    },
  },
  tasks: {
    status: "success",
    value: {
      apiContract: "omi",
      accountEpoch: null,
      items:
        example === "empty"
          ? []
          : [
              "Send the notes from today’s conversation",
              "Make time for a long walk",
              "Review the ideas for the next release",
            ].map((title, index) => ({
              kind: "task",
              id: `preview-task-${index}`,
              title,
              summary: "",
              searchableText: title,
              completed: index === 1,
              completedAt: null,
              dueAt: null,
              owner: null,
              source: "desktop",
              provenance: [],
              sortOrder: index,
              indentLevel: 0,
              createdAt: null,
              updatedAt: null,
              revision: null,
            })),
      page,
    },
  },
};

function Preview() {
  const [signedIn, setSignedIn] = useState(false);
  const [complete, setComplete] = useState(false);
  const [draft, setDraft] = useState("");
  const [chatOpen, setChatOpen] = useState(chatState !== null);
  const [chatBusy, setChatBusy] = useState(chatState === "waiting");
  const [chatError, setChatError] = useState<string | null>(
    chatState === "error"
      ? "Example error: your message could not be sent. Try again."
      : null
  );
  const [deviceOpen, setDeviceOpen] = useState(deviceState !== null);
  const [deviceNote, setDeviceNote] = useState<string | null>(
    deviceState === "error"
      ? "Example connection error. Check Bluetooth and try again."
      : null
  );
  const [mode, setMode] = useState<MobileOmnibarMode>("Search");
  const [chatExpanded, setChatExpanded] = useState(chatState === "long");
  const composerRef = useRef<TextInput>(null);
  const scrollRef = useRef<ScrollView>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(
    chatState === "ready" || chatState === "waiting" || chatState === "long"
      ? [
          {
            id: "example-human",
            sender: "human",
            text: "Help me turn these ideas into a plan.",
            createdAt: 1789641000,
            generationOutcome: null,
          },
          {
            id: "example-ai",
            sender: "ai",
            text:
              chatState === "waiting"
                ? ""
                : chatState === "long"
                ? `${"Here is a longer answer grounded in the loaded timeline. ".repeat(
                    18
                  )}\n\n1. Gather your notes.\n2. Pick the idea that matters most.\n3. Give it a little time today.`
                : "Start with one useful next step.\n\n1. Gather your notes.\n2. Pick the idea that matters most.\n3. Give it a little time today.",
            createdAt: 1789641060,
            generationOutcome: chatState === "waiting" ? null : "completed",
            generationId: "example-generation",
          },
        ]
      : []
  );
  const previewSend = () => {
    if (!chatOpen) beforeChat.current = route;
    setRoute("home");
    setChatOpen(true);
    setChatError("Preview only — messages are not sent.");
  };
  const [route, setRoute] = useState<MobileRoute>(
    conversationState ? "chat" : "home"
  );
  const beforeChat = useRef<MobileRoute>("home");
  const [conversationNotice, setConversationNotice] = useState<string | null>(
    null
  );
  const [outcomes, setOutcomes] = useState<DesktopReadOutcomes | null>(
    example === "example" || example === "empty" ? exampleOutcomes : null
  );
  const updateTask = (
    id: string,
    change: (task: TaskProjection) => TaskProjection
  ) =>
    setOutcomes((current) =>
      current?.tasks.status === "success"
        ? {
            ...current,
            tasks: {
              ...current.tasks,
              value: {
                ...current.tasks.value,
                items: current.tasks.value.items.map((task) =>
                  task.id === id ? change(task) : task
                ),
              },
            },
          }
        : current
    );
  const taskActions = {
    writesAvailable: outcomes !== null,
    onTaskToggle: (id: string) =>
      updateTask(id, (task) => ({ ...task, completed: !task.completed })),
    onTaskEdit: (id: string, title: string) =>
      updateTask(id, (task) => ({ ...task, title, searchableText: title })),
  };
  const desktop =
    surface === "desktop" || (complete && !surface.startsWith("mobile"));
  useEffect(() => {
    document.body.dataset.preview = surface.startsWith("mobile")
      ? "mobile"
      : desktop
      ? "app"
      : "setup";
  }, [desktop]);
  return h(
    SafeAreaProvider,
    null,
    h(
      View,
      { style: { flex: 1 }, nativeID: "preview-desktop" },
      h(
        View,
        { nativeID: "preview-window", style: { flex: 1 } },
        desktop
          ? h(DesktopApp, {
              session: "ready",
              reads:
                outcomes?.conversations.status === "success"
                  ? outcomes.conversations.value.items
                  : [],
              outcomes,
              readsPhase: outcomes ? "ready" : "unavailable",
              ...taskActions,
              activeGenerationId: null,
              authError: null,
              signingIn: false,
              draft,
              messages: [],
              hasOlderChat: false,
              loadingOlderChat: false,
              chatBusy: false,
              chatError: null,
              onRefresh: noop,
              onSignIn: noop,
              onSignOut: () => setComplete(false),
              onDraftChange: setDraft,
              onLoadOlderChat: noop,
              onSend: noop,
              onStop: noop,
            })
          : surface === "mobile" || (surface === "mobile-setup" && complete)
          ? h(MobileAppSurface, {
              ...taskActions,
              activeRoute: route,
              onRouteChange: (next) => {
                setChatOpen(false);
                setRoute(next);
              },
              chatContent: chatOpen
                ? h(MobileChat, {
                    messages: chatMessages,
                    busy: chatBusy,
                    error: chatError,
                    loadingHistory: chatState === "loading",
                    hasOlder: false,
                    loadingOlder: false,
                    onLoadOlder: noop,
                    onClose: () => {
                      setChatOpen(false);
                      setChatExpanded(false);
                      setRoute(beforeChat.current);
                    },
                    presentation:
                      chatExpanded ||
                      chatMessages.some(
                        (message) =>
                          message.sender === "ai" && message.text.length > 420
                      )
                        ? "overlay"
                        : "compact",
                    onExpand: () => setChatExpanded(true),
                    onRemember: () =>
                      setChatError(
                        "Preview only — authenticated memory saving is not available here."
                      ),
                    prompts: [
                      "What should I remember?",
                      "Help me find a next step",
                    ],
                    onUsePrompt: (prompt) => {
                      setDraft(prompt);
                      composerRef.current?.focus();
                    },
                    shouldAnimate: () => false,
                    scrollRef,
                    onScroll: noop,
                  })
                : undefined,
              chatOverlay:
                chatExpanded ||
                chatMessages.some(
                  (message) =>
                    message.sender === "ai" && message.text.length > 420
                ),
              omnibar: h(MobileOmnibar, {
                key: "mobile-omnibar",
                mode,
                onModeChange: (next) => {
                  setMode(next);
                  if (next === "Search" && chatOpen) {
                    setChatOpen(false);
                    setRoute("home");
                  }
                },
                value: draft,
                onChange: setDraft,
                inputRef: composerRef,
                busy: chatBusy,
                canStop: chatBusy,
                onSubmit: () => {
                  if (mode === "Ask") previewSend();
                  else {
                    setChatOpen(false);
                    setRoute("home");
                  }
                },
                onStop: () => {
                  setChatBusy(false);
                  setChatMessages((current) =>
                    current.map((message) =>
                      message.sender === "ai"
                        ? { ...message, generationOutcome: "cancelled" }
                        : message
                    )
                  );
                },
                liveControl: h(LiveVoiceButton, {
                  backend: null,
                  dock: true,
                }),
              }),
              searchQuery: mode === "Search" ? draft : "",
              conversations:
                outcomes?.conversations.status === "success"
                  ? outcomes.conversations.value.items.map((item) => ({
                      kind: "conversation" as const,
                      id: item.id,
                      title: item.title,
                      summary: item.summary,
                      searchableText: item.searchableText,
                      atMs: Date.parse(item.startedAt ?? item.createdAt),
                    }))
                  : [],
              memories:
                outcomes?.memories.status === "success"
                  ? outcomes.memories.value.items.map((item) => ({
                      kind: "memory" as const,
                      id: item.id,
                      title: item.title,
                      summary: item.summary,
                      searchableText: item.searchableText,
                      atMs:
                        item.timestamp === null ? null : item.timestamp * 1000,
                      source: "backend" as const,
                    }))
                  : [],
              recall:
                example === "example"
                  ? [
                      {
                        kind: "recall" as const,
                        id: "preview-recall-1",
                        appName: "Figma",
                        windowTitle: "Viewed roadmap designs",
                        searchableText: "Figma roadmap designs",
                        atMs: Date.parse(exampleToday(9, 12)),
                        source: "captured" as const,
                        local: true,
                      },
                      {
                        kind: "recall" as const,
                        id: "preview-recall-2",
                        appName: "Slack",
                        windowTitle: "Viewed team updates",
                        searchableText: "Slack team updates",
                        atMs: Date.parse(exampleToday(8, 3)),
                        source: "captured" as const,
                        local: true,
                      },
                      {
                        kind: "recall" as const,
                        id: "preview-recall-3",
                        appName: "Chrome",
                        windowTitle: "Read competitor analysis",
                        searchableText: "Chrome competitor analysis",
                        atMs: Date.parse(exampleYesterday(14, 17)),
                        source: "shipping" as const,
                        local: true,
                      },
                    ]
                  : [],
              timelineStatus: outcomes ? "ready" : "offline",
              capture: {
                active:
                  deviceState !== null && previewDevice.capture === "recording",
                waitingForAudio: deviceState === "waiting",
                transcript: "",
              },
              device: {
                connected:
                  deviceState !== null && previewDevice.phase === "connected",
                label: deviceState
                  ? homeConnectionStatus(previewDevice).label
                  : "Connect Omi",
              },
              devicePanel: deviceOpen
                ? h(DeviceSession, {
                    variant: "compact",
                    nativeSnapshot: deviceState ? previewDevice : null,
                    deviceBusy: deviceState === "connecting",
                    deviceScanMessage: deviceNote,
                    onScan: () =>
                      setDeviceNote(
                        "Preview only — Bluetooth scanning is not started."
                      ),
                    onToggle: () =>
                      setDeviceNote(
                        "Preview only — no device connection is changed."
                      ),
                  })
                : undefined,
              tasks:
                outcomes?.tasks.status === "success"
                  ? outcomes.tasks.value.items
                  : [],
              taskStatus: outcomes ? "ready" : "offline",
              conversationContent: h(ConversationsPage, {
                embedded: true,
                search: {
                  value: mode === "Search" ? draft : "",
                  onChange: (value) => {
                    if (mode === "Search") setDraft(value);
                  },
                },
                loading: conversationState === "loading",
                notice: conversationNotice,
                outcome:
                  conversationState === "loading"
                    ? null
                    : conversationState === "error"
                    ? {
                        status: "error",
                        error:
                          "Example connection error. Your saved conversations could not be loaded. Try refreshing.",
                      }
                    : outcomes?.conversations ?? {
                        status: "error",
                        error: "Conversations unavailable in this preview.",
                      },
              }),
              settingsContent: h(SettingsPage),
              appsContent: h(ConnectorsPage),
              onOpenDevice: () => setDeviceOpen((open) => !open),
              onOpenSettings: () => setRoute("settings"),
            })
          : h(surface === "mobile-setup" ? Onboarding : DesktopOnboarding, {
              onSignIn: () => setSignedIn(true),
              signingIn: false,
              setupRequired: signedIn,
              onCompleteSetup: () => setComplete(true),
              onSignOut: () => setSignedIn(false),
            })
      )
    )
  );
}

if (import.meta.env.DEV) {
  // Even when a developer configures the authenticated proxy, this review
  // entry must neither read an account nor persist preview onboarding choices.
  omiBackend.request = async (request) => ({
    id: request.id,
    status: 503,
    body: null,
    retryAfterSeconds: null,
  });
  omiBackend.uploadAudioFile = async () => ({
    id: "preview",
    status: 503,
    body: null,
    retryAfterSeconds: null,
  });
  document.body.dataset.preview = surface.startsWith("mobile")
    ? "mobile"
    : surface === "desktop"
    ? "app"
    : "setup";
  AppRegistry.registerComponent("OmiDesignPreview", () => Preview);
  AppRegistry.runApplication("OmiDesignPreview", {
    rootTag: document.getElementById("app"),
  });
}
