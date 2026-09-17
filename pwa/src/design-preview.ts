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
// Explicitly labelled, local-only fixtures for populated/empty layout review.
const exampleOutcomes: DesktopReadOutcomes = {
  conversations: {
    status: "success",
    value: {
      items:
        example === "empty"
          ? []
          : [
              "A thoughtful start to the week",
              "Planning a quieter workspace",
            ].map((title, index) => ({
              kind: "conversation",
              id: `preview-conversation-${index}`,
              title,
              summary:
                index === 0
                  ? "A few ideas, a clear next step, and time to think."
                  : "Less visual noise. More room for the work that matters.",
              searchableText: title,
              createdAt: "2026-09-17T10:00:00Z",
              updatedAt: "2026-09-17T10:30:00Z",
              startedAt: "2026-09-17T10:00:00Z",
              finishedAt: "2026-09-17T10:30:00Z",
              starred: index === 1,
              status: "completed",
              source: "desktop",
              visibility: "private",
              folderId: null,
              locked: false,
              discarded: false,
            })),
      page,
    },
  },
  memories: { status: "success", value: { items: [], page } },
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
  const [mode, setMode] = useState<MobileOmnibarMode>("Ask");
  const composerRef = useRef<TextInput>(null);
  const scrollRef = useRef<ScrollView>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(
    chatState === "ready" || chatState === "waiting"
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
        Text,
        {
          nativeID: "preview-notice",
          style: {
            color: "#666a62",
            backgroundColor: "#eeeee8",
            textAlign: "center",
            padding: 6,
            fontSize: 11,
          },
        },
        `${
          example
            ? "EXAMPLE DATA · Edits stay in this preview · "
            : "COMPONENT PREVIEW · "
        }${
          surface.startsWith("mobile")
            ? "Mobile browser preview · Simulated controls · Nothing sent or recorded"
            : "Glass is approximated in the browser · Native windows require macOS"
        }`
      ),
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
                      setRoute(beforeChat.current);
                    },
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
              recall:
                example === "example"
                  ? [
                      {
                        kind: "recall" as const,
                        id: "preview-recall-1",
                        appName: "Notes",
                        windowTitle: "Example screen history",
                        searchableText: "Notes Example screen history",
                        atMs: Date.parse("2026-09-17T09:12:00Z"),
                        source: "captured" as const,
                        local: true,
                      },
                    ]
                  : [],
              timelineStatus: outcomes ? "ready" : "offline",
              timelineNotice:
                example === "example"
                  ? "Preview only — Recall is not saved from this browser."
                  : null,
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
              liveVoiceControl: h(LiveVoiceButton, {
                backend: null,
                compact: true,
              }),
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
