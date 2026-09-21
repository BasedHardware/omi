import React, { useState } from "react";
import {
  ArrowUp,
  ArrowUpRight,
  CheckCheck,
  Home,
  History,
  MessageCircle,
  MessageSquare,
  Settings,
  Sun,
  Moon,
  Search,
  Monitor,
  MonitorDot,
} from "lucide-react";
import { homeBriefing } from "../../../react-native/src/desktop/homeBriefing";
import { OmiAvatar } from "../../../react-native/src/ui/OmiAvatar";
import { useReduceMotion } from "../../../react-native/src/app/useReduceMotion.web";
import type { ReadsPhase } from "../../../react-native/src/app/useDesktopReads";
import type { DesktopReadOutcomes } from "../../../react-native/src/desktopReadClient";
import {
  Button,
  Input,
  Checkbox,
  Card,
  CardHeader,
  CardTitle,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "./components";

const routes = [
  { label: "Home", icon: Home },
  { label: "Chat", icon: MessageSquare, desktop: true },
  { label: "Conversations", icon: MessageCircle },
  { label: "Recall", icon: History, desktop: true },
  { label: "Tasks", icon: CheckCheck },
  { label: "Settings", icon: Settings },
];

export function Preview({
  initialOutcomes,
  initialPhase = "ready",
  mobile = false,
}: {
  initialOutcomes: DesktopReadOutcomes;
  initialPhase?: ReadsPhase;
  mobile?: boolean;
}) {
  const [outcomes, setOutcomes] = useState(initialOutcomes);
  const [route, setRoute] = useState("Home");
  const [mode, setMode] = useState(mobile ? "Search" : "Ask");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [dark, setDark] = useState(mobile);
  const [recallEnabled, setRecallEnabled] = useState(false);
  const reduceMotion = useReduceMotion();
  const brief = homeBriefing(outcomes, initialPhase);
  const searching = mode === "Search" && query.trim() !== "";
  const matches = (text: string) =>
    !searching ||
    text.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  const tasks =
    outcomes.tasks.status === "success" ? outcomes.tasks.value.items : [];
  const conversations =
    outcomes.conversations.status === "success"
      ? outcomes.conversations.value.items
      : [];
  const visibleTasks = tasks.filter((task) => matches(task.title));
  const visibleConversations = conversations.filter((item) =>
    matches(`${item.title} ${item.summary}`)
  );
  const ready = initialPhase === "ready";
  const tasksReady = ready && outcomes.tasks.status === "success";
  const conversationsReady =
    ready && outcomes.conversations.status === "success";
  const navigation = (
    <TabsList aria-label="Main navigation" className="main-nav">
      {routes
        .filter(({ label, desktop }) =>
          mobile ? !desktop : label !== "Settings"
        )
        .map(({ label, icon: Icon }) => (
          <TabsTrigger key={label} value={label}>
            {mobile && label === "Home" ? (
              <OmiAvatar
                tone="ink"
                size={24}
                inkColor="currentColor"
                motion={route === "Home" ? "breathe" : undefined}
                reduceMotion={reduceMotion}
              />
            ) : (
              <Icon aria-hidden="true" />
            )}
            <span>{label}</span>
          </TabsTrigger>
        ))}
    </TabsList>
  );
  const taskList = (
    <Card aria-label="Tasks">
      <CardHeader>
        <CardTitle>Tasks</CardTitle>
        {route === "Home" && (
          <Button variant="ghost" onClick={() => setRoute("Tasks")}>
            View all <ArrowUpRight />
          </Button>
        )}
      </CardHeader>
      {!tasksReady ? (
        <p className="muted">Tasks are not loaded yet.</p>
      ) : visibleTasks.length === 0 ? (
        <p className="muted">
          {searching ? "No tasks match this search." : "No tasks yet."}
        </p>
      ) : (
        <ul className="rows">
          {visibleTasks.map((task) => (
            <li key={task.id} className="task-row">
              <Checkbox
                aria-label={`Complete ${task.title}`}
                checked={task.completed}
                onCheckedChange={(completed) =>
                  setOutcomes((current) =>
                    current.tasks.status !== "success"
                      ? current
                      : {
                          ...current,
                          tasks: {
                            ...current.tasks,
                            value: {
                              ...current.tasks.value,
                              items: current.tasks.value.items.map((item) =>
                                item.id === task.id
                                  ? { ...item, completed }
                                  : item
                              ),
                            },
                          },
                        }
                  )
                }
              />
              <div>
                <p className={task.completed ? "completed" : "font-medium"}>
                  {task.title}
                </p>
                <p className="meta">
                  {task.completed
                    ? "Completed"
                    : task.dueAt === null
                    ? "On your list"
                    : "Due today"}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
  const conversationList = (
    <Card aria-label="Conversations and memories">
      <CardHeader>
        <CardTitle>Conversations & memories</CardTitle>
        {route === "Home" && (
          <Button
            variant="ghost"
            aria-label="View all conversations"
            onClick={() => setRoute("Conversations")}
          >
            <ArrowUpRight />
          </Button>
        )}
      </CardHeader>
      {!conversationsReady ? (
        <p className="muted">Conversations are not loaded yet.</p>
      ) : visibleConversations.length === 0 ? (
        <p className="muted">
          {searching
            ? "Nothing captured matches this search."
            : "Nothing captured yet."}
        </p>
      ) : (
        <ul className="rows">
          {visibleConversations.map((item) => (
            <li key={item.id} className="conversation-row">
              <MessageCircle className="row-icon" aria-hidden="true" />
              <div>
                <h3 className="font-medium">{item.title}</h3>
                <p className="muted summary">{item.summary}</p>
                <p className="meta">Today · Conversation</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
  return (
    <div className={`preview-stage ${mobile ? "mobile-stage" : ""}`}>
      <p className="preview-notice">
        BASE UI + SHADCN · Example data · Edits stay in this preview
      </p>
      <Tabs
        value={route}
        onValueChange={(value) => {
          setRoute(String(value));
          setNotice("");
        }}
        className="omi-window"
        data-theme={dark ? "dark" : "light"}
      >
        {!mobile && (
          <header className="window-header">
            <div
              className="traffic-lights"
              role="img"
              aria-label="macOS window controls (visual preview only)"
              title="Native window controls — visual preview only"
            >
              <span className="traffic-close" />
              <span className="traffic-minimize" />
              <span className="traffic-zoom" />
            </div>
            {navigation}
            <div className="header-actions">
              <Button
                variant="ghost"
                size="icon"
                className="recall-toggle"
                aria-label="Recall capture preview"
                aria-pressed={recallEnabled}
                title={
                  recallEnabled
                    ? "Recall on — preview only"
                    : "Recall off — preview only"
                }
                onClick={() => setRecallEnabled((value) => !value)}
              >
                {recallEnabled ? (
                  <MonitorDot aria-hidden="true" />
                ) : (
                  <Monitor aria-hidden="true" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Settings"
                title="Settings"
                aria-current={route === "Settings" ? "page" : undefined}
                onClick={() => {
                  setRoute("Settings");
                  setNotice("");
                }}
              >
                <Settings aria-hidden="true" />
              </Button>
            </div>
          </header>
        )}
        <form
          className="omnibar"
          aria-label="Omi omnibar"
          onSubmit={(event) => {
            event.preventDefault();
            if (mode === "Search") {
              setRoute("Home");
              setNotice("");
            } else
              setNotice(
                mode === "Recall"
                  ? "Screen history requires the native Mac app. Nothing is captured in this preview."
                  : "Preview only — your question is not sent."
              );
          }}
        >
          <div className="mode-buttons" role="group" aria-label="Omnibar mode">
            {[
              { value: "Ask", icon: MessageCircle },
              { value: "Search", icon: Search },
              { value: "Recall", icon: History },
            ]
              .filter(({ value }) => !mobile || value !== "Recall")
              .map(({ value, icon: Icon }) => (
                <Button
                  key={value}
                  variant="ghost"
                  size="icon"
                  aria-label={`${value} mode`}
                  title={value}
                  aria-pressed={mode === value}
                  className={mode === value ? "mode-active" : ""}
                  onClick={() => {
                    setMode(value);
                    setNotice("");
                  }}
                >
                  <Icon aria-hidden="true" />
                </Button>
              ))}
          </div>
          <Input
            aria-label={
              mode === "Ask"
                ? "Ask Omi"
                : mode === "Recall"
                ? "Search Recall"
                : "Search history"
            }
            placeholder={
              mode === "Ask"
                ? mobile
                  ? "Ask Omi…"
                  : "Ask about your day…"
                : mode === "Recall"
                ? "Find a moment on your screen…"
                : mobile
                ? "Search your day…"
                : "Find something in your day…"
            }
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              if (mode === "Search") setRoute("Home");
            }}
            className="omnibar-input"
          />
          <Button
            type="submit"
            size="icon"
            aria-label={mode === "Ask" ? "Send question" : "Submit search"}
            disabled={!query.trim()}
            className="rounded-full"
          >
            <ArrowUp />
          </Button>
        </form>
        {notice && (
          <p role="status" className="transport-notice">
            {notice}
          </p>
        )}
        <main className="workspace">
          <TabsContent value="Home">
            <div className="brief" aria-live="polite">
              <h1>{searching ? "A little easier to find." : brief.title}</h1>
              <p>
                {searching
                  ? `Results from loaded history for “${query.trim()}”`
                  : brief.subtitle}
              </p>
            </div>
            <div className="home-columns">
              {taskList}
              {conversationList}
            </div>
          </TabsContent>
          <TabsContent value="Tasks">
            <div className="brief">
              <h1>Tasks</h1>
              <p>Make room for what matters next.</p>
            </div>
            {taskList}
          </TabsContent>
          <TabsContent value="Conversations">
            <div className="brief">
              <h1>Conversations</h1>
              <p>Your recent context, ready when you need it.</p>
            </div>
            {conversationList}
          </TabsContent>
          {!mobile && (
            <TabsContent value="Chat">
              <div className="brief">
                <h1>Ask about your day.</h1>
                <p>
                  Choose Ask in the omnibar. Questions are not sent in this
                  preview.
                </p>
              </div>
            </TabsContent>
          )}
          {!mobile && (
            <TabsContent value="Recall">
              <div className="brief">
                <h1>Screen history</h1>
                <p>Screen capture and Recall require the native Mac app.</p>
              </div>
              <Card>
                <p className="muted">
                  No screen content is captured or stored here.
                </p>
              </Card>
            </TabsContent>
          )}
          <TabsContent value="Apps">
            <div className="brief">
              <h1>Apps</h1>
              <p>Bring more of your day together.</p>
            </div>
            <Card>
              <p className="muted">
                Connections are not available in this local preview.
              </p>
            </Card>
          </TabsContent>
          <TabsContent value="Settings" aria-label="Settings">
            <div className="brief">
              <h1>Settings</h1>
              <p>Your space, your preferences.</p>
            </div>
            <Card>
              <div className="setting-row">
                <div>
                  <CardTitle>Appearance</CardTitle>
                  <p className="muted mt-1">Only changes this preview.</p>
                </div>
                <Button
                  variant="outline"
                  onClick={() => setDark((value) => !value)}
                >
                  {dark ? <Sun /> : <Moon />}
                  {dark ? "Use light theme" : "Use dark theme"}
                </Button>
              </div>
              <div className="setting-row">
                <CardTitle>Apps</CardTitle>
                <Button variant="ghost" onClick={() => setRoute("Apps")}>
                  Explore apps <ArrowUpRight />
                </Button>
              </div>
            </Card>
          </TabsContent>
        </main>
        {mobile && navigation}
      </Tabs>
    </div>
  );
}
