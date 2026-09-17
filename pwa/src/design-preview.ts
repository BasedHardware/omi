// Development-only component review. This does not mount the authenticated
// orchestrator or persist setup. Vite's production entry remains index.html.
import React, { useEffect, useState } from "react";
import { AppRegistry, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { DesktopOnboarding } from "../../react-native/src/desktop/DesktopOnboarding";
import { DesktopApp } from "../../react-native/src/desktop/DesktopApp";
import { Onboarding } from "../../react-native/src/ui/Onboarding";
import { ConversationsPage } from "../../react-native/src/pages/Conversations";
import { SettingsPage } from "../../react-native/src/pages/Settings";
import { ConnectorsPage } from "../../react-native/src/pages/Connectors";
import { omiBackend } from "../../react-native/src/omiNative.web";
import type {
  DesktopReadOutcomes,
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
              starred: false,
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
  const [route, setRoute] = useState<MobileRoute>("home");
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
            ? "Mobile browser preview · Not a native device"
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
              onRouteChange: setRoute,
              capture: { active: false, transcript: "" },
              device: { connected: false, label: "Connect Omi" },
              tasks:
                outcomes?.tasks.status === "success"
                  ? outcomes.tasks.value.items
                  : [],
              taskStatus: outcomes ? "ready" : "offline",
              recaps:
                outcomes?.conversations.status === "success"
                  ? outcomes.conversations.value.items.map((item) => ({
                      id: item.id,
                      title: item.title,
                      dateLabel: "Example recap",
                    }))
                  : [],
              recapStatus: outcomes ? "ready" : "offline",
              mindMapStatus: "empty",
              conversationContent: h(ConversationsPage, {
                embedded: true,
                loading: false,
                outcome: outcomes?.conversations ?? {
                  status: "error",
                  error: "Conversations unavailable in this preview.",
                },
              }),
              settingsContent: h(SettingsPage),
              appsContent: h(ConnectorsPage),
              askValue: draft,
              onAskChange: setDraft,
              onAskSubmit: noop,
              onOpenSettings: () => setRoute("settings"),
              onOpenDevice: noop,
              onOpenCalls: noop,
              onViewTasks: () => setRoute("tasks"),
              onViewRecaps: () => setRoute("chat"),
              onExpandMindMap: noop,
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
