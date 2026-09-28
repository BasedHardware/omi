// Development-only component review. This does not mount the authenticated
// orchestrator or persist setup. Vite's production entry remains index.html.
import React, { useEffect, useRef, useState } from "react";
import { AppRegistry, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { DesktopOnboarding } from "../../react-native/src/desktop/DesktopOnboarding";
import { DesktopApp } from "../../react-native/src/desktop/DesktopApp";
import { DesktopThemeProvider } from "../../react-native/src/desktop/DesktopTheme";
import { Onboarding } from "../../react-native/src/ui/Onboarding";
import { ConversationsPage } from "../../react-native/src/pages/Conversations";
import { SettingsPage } from "../../react-native/src/pages/Settings";
import { ConnectorsPage } from "../../react-native/src/pages/Connectors";
import { MobileChat } from "../../react-native/src/mobile/MobileChat";
import {
  MobileOmnibar,
  type MobileOmnibarMode,
} from "../../react-native/src/mobile/MobileOmnibar";
import { ProjectionList } from "../../react-native/src/ui/ProjectionList";
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
import {
  MobileThemeRoot,
  type MobileAppearance,
} from "../../react-native/src/mobile/MobileTheme";
import "./root.css";
import "./preview-fonts.css";

const h = React.createElement;
const noop = () => undefined;
const surface = new URLSearchParams(location.search).get("surface") ?? "setup";
const example = new URLSearchParams(location.search).get("data");
const chatState = new URLSearchParams(location.search).get("chat");
const deviceState = new URLSearchParams(location.search).get("device");
const conversationState = new URLSearchParams(location.search).get(
  "conversations"
);
// Screenshot controls (see pwa/visual-audit/). All optional; defaults match
// the interactive preview.
const params = new URLSearchParams(location.search);
const appearance = params.get("appearance") === "light" ? "light" : "dark";
const initialRouteParam = params.get("route");
const initialFilterParam = params.get("filter");
const showNotice = params.get("notice") !== "off";
// Mobile only: pin the phone frame to the audited width (see
// design-preview.html) instead of centring a 430 px frame.
const phoneFrame = Number(params.get("frame"));
const desktopRoutes = ["Home", "Rewind", "Settings", "Chat"] as const;
const desktopFilters = ["all", "conversations", "recall", "tasks"] as const;
const mobileRoutes = ["home", "chat", "tasks", "apps", "settings"] as const;
const pick = <T extends string>(
  value: string | null,
  allowed: readonly T[]
): T | undefined =>
  allowed.find((item) => item.toLowerCase() === value?.toLowerCase());
const desktopInitialRoute = pick(initialRouteParam, desktopRoutes);
// Desktop-only review hooks: a Settings pane (`pane=account`), the v5 pages
// interface (`ui=v5`) and its rail route (`v5route=conversations`).
const desktopSettingsPanes = [
  "General",
  "Account & Plan",
  "Transcription",
  "Rewind",
  "Alerts & Privacy",
  "AI & Automation",
  "Apps",
  "About",
] as const;
const desktopInitialPane = desktopSettingsPanes.find((pane) =>
  pane.toLowerCase().startsWith((params.get("pane") ?? "\u0000").toLowerCase())
);
const desktopUiVersion = params.get("ui") === "v5" ? "v5" : undefined;
const desktopV5Route = pick(params.get("v5route"), [
  "Home",
  "Chat",
  "Conversations",
  "Rewind",
  "Tasks",
  "Settings",
] as const);
const desktopInitialFilter = pick(initialFilterParam, desktopFilters);
const mobileInitialRoute = pick(initialRouteParam, mobileRoutes);
const day = (offsetDays: number, hour: number, minute = 0) => {
  const at = new Date(Date.UTC(2026, 8, 17 - offsetDays, hour, minute));
  return at.toISOString();
};
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
const previewConversations: [string, string, number, number][] = [
  [
    "A thoughtful start to the week",
    "A few ideas, a clear next step, and time to think.",
    0,
    10,
  ],
  [
    "Planning a quieter workspace",
    "Less visual noise. More room for the work that matters.",
    0,
    15,
  ],
  [
    "Design review: onboarding",
    "Priya walked through the new permission guide; two copy changes and one layout fix agreed.",
    1,
    11,
  ],
  [
    "Coffee with Sam",
    "Talked about the trip in October and a book recommendation worth following up on.",
    1,
    16,
  ],
  [
    "Weekly planning",
    "Priorities for the release, owners for each task, and a date for the next check-in.",
    2,
    9,
  ],
  ["", "A short recording with no title yet.", 3, 14],
];
const previewMemories = [
  "Prefers morning meetings before 11am",
  "Is planning a trip to Lisbon in October",
  "Leads the onboarding redesign with Priya",
  "Reads before bed; currently on a history of the printing press",
  "Allergic to peanuts",
];
const exampleOutcomes: DesktopReadOutcomes = {
  conversations: {
    status: "success",
    value: {
      items:
        example === "empty"
          ? []
          : previewConversations.map(
              ([title, summary, offset, hour], index) => ({
                kind: "conversation",
                id: `preview-conversation-${index}`,
                title,
                summary,
                searchableText: `${title} ${summary}`,
                createdAt: day(offset, hour),
                updatedAt: day(offset, hour, 30),
                startedAt: day(offset, hour),
                finishedAt: day(offset, hour, 30),
                starred: index === 1,
                status: "completed",
                source: "desktop",
                visibility: "private",
                folderId: null,
                locked: false,
                discarded: false,
              })
            ),
      page,
    },
  },
  memories: {
    status: "success",
    value: {
      apiContract: "omi",
      items:
        example === "empty"
          ? []
          : previewMemories.map((text, index) => ({
              kind: "memory",
              id: `preview-memory-${index}`,
              visibility: index === 2 ? "public" : "private",
              title: text,
              summary: text,
              searchableText: text,
              citations: index === 0 ? ["preview-conversation-0"] : [],
              timestamp: Date.parse(day(index, 9)),
              provenance: {
                label: index === 0 ? "From a conversation" : null,
                synthesisVersion: null,
                inputDigest: null,
                outputDigest: null,
              },
            })),
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
              "Book the design review with Priya",
              "Reply to the onboarding feedback thread",
            ].map((title, index) => ({
              kind: "task",
              id: `preview-task-${index}`,
              title,
              summary: "",
              searchableText: title,
              completed: index === 1,
              completedAt: null,
              dueAt: index === 0 ? Date.parse("2026-09-18T12:00:00Z") : null,
              owner: index === 0 ? "You" : null,
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
  const [draft, setDraft] = useState(params.get("q") ?? "");
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
  const [mobileAppearance, setMobileAppearance] =
    useState<MobileAppearance>(appearance);
  const [mode, setMode] = useState<MobileOmnibarMode>(
    chatState ? "Ask" : "Search"
  );
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
    mobileInitialRoute ?? (conversationState ? "chat" : "home")
  );
  const beforeChat = useRef<MobileRoute>("home");
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
  const onboardingProps = {
    onSignIn: () => setSignedIn(true),
    signingIn: false,
    setupRequired: signedIn,
    onCompleteSetup: () => setComplete(true),
    onSignOut: () => setSignedIn(false),
  };
  const desktop =
    surface === "desktop" || (complete && !surface.startsWith("mobile"));
  const mobileRoot = (child: React.ReactElement) =>
    h(
      MobileThemeRoot,
      {
        appearance: mobileAppearance,
        onAppearanceChange: setMobileAppearance,
      },
      child
    );
  useEffect(() => {
    document.body.dataset.appearance = surface.startsWith("mobile")
      ? mobileAppearance === "light"
        ? "light"
        : "dark"
      : appearance;
    if (surface.startsWith("mobile") && phoneFrame > 0) {
      document.body.style.setProperty(
        "--preview-phone-width",
        `${phoneFrame}px`
      );
      document.body.style.setProperty("--preview-phone-align", "flex-start");
      document.body.style.setProperty("--preview-phone-margin", "0");
    }
    document.body.dataset.preview = surface.startsWith("mobile")
      ? "mobile"
      : desktop
      ? "app"
      : "setup";
  }, [desktop, mobileAppearance]);
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
            display: showNotice ? "flex" : "none",
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
              initialAppearance: appearance,
              initialRoute: desktopInitialRoute,
              initialActivityFilter: desktopInitialFilter,
              initialChatOpen: chatState !== null,
              initialSettingsPane: desktopInitialPane,
              initialUiVersion: desktopUiVersion,
              initialV5Route: desktopV5Route,
              outcomes,
              readsPhase: outcomes ? "ready" : "unavailable",
              ...taskActions,
              activeGenerationId: null,
              authError: null,
              signingIn: false,
              draft,
              messages: chatMessages,
              hasOlderChat: false,
              loadingOlderChat: false,
              loadingHistory: chatState === "loading",
              chatBusy,
              chatError,
              onRefresh: noop,
              onSignIn: noop,
              onSignOut: () => setComplete(false),
              onDraftChange: setDraft,
              onLoadOlderChat: noop,
              onSend: noop,
              onStop: noop,
            })
          : surface === "mobile" || (surface === "mobile-setup" && complete)
          ? mobileRoot(
              h(MobileAppSurface, {
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
                searchContent:
                  mode === "Search" && draft.trim() !== ""
                    ? h(ProjectionList, {
                        items: Object.values(outcomes ?? {})
                          .flatMap<DesktopReadProjection>((outcome) =>
                            outcome.status === "success"
                              ? outcome.value.items
                              : []
                          )
                          .filter((item) =>
                            item.searchableText
                              .toLowerCase()
                              .includes(draft.trim().toLowerCase())
                          ),
                        loading: false,
                        error: outcomes
                          ? null
                          : "Saved data unavailable in this preview.",
                        emptyTitle: "No Matches",
                        emptyCopy:
                          "Search covers data already loaded on this device.",
                      })
                    : undefined,
                capture: {
                  active:
                    deviceState !== null &&
                    previewDevice.capture === "recording",
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
                conversations:
                  outcomes?.conversations.status === "success"
                    ? outcomes.conversations.value.items
                    : [],
                conversationStatus: outcomes ? "ready" : "offline",
                conversationContent: h(ConversationsPage, {
                  embedded: true,
                  initialSelectedId: params.get("conversation"),
                  search: {
                    value: mode === "Search" ? draft : "",
                    onChange: (value) => {
                      if (mode === "Search") setDraft(value);
                    },
                  },
                  loading: conversationState === "loading",
                  outcome:
                    conversationState === "loading"
                      ? null
                      : conversationState === "error"
                      ? {
                          status: "error",
                          error:
                            "Example connection error. Your saved conversations could not be loaded.",
                        }
                      : outcomes?.conversations ?? {
                          status: "error",
                          error: "Conversations unavailable in this preview.",
                        },
                }),
                settingsContent: h(SettingsPage, {
                  onOpenApps: () => setRoute("apps"),
                }),
                appsContent: h(ConnectorsPage),
                onOpenDevice: () => setDeviceOpen((open) => !open),
                onViewTasks: () => setRoute("tasks"),
                onViewConversations: () => setRoute("chat"),
              })
            )
          : surface === "mobile-setup"
          ? mobileRoot(h(Onboarding, onboardingProps))
          : // The app mounts desktop onboarding inside DesktopThemeProvider
            // (AppOrchestrator and DesktopApp's signed-out gate), so the
            // preview does too: light glass gets dark ink.
            h(DesktopThemeProvider, {
              initialName: appearance,
              children: h(DesktopOnboarding, onboardingProps),
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
