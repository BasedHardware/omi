(() => {
  const PENDING = "OMI_CONTROL_PENDING";
  const SCHEMA = "omi.control-acceptance.v1";
  const KEY = "omi.control-acceptance.v1";
  const HOME_FAILURE_NOTICE = "Showing saved data. Couldn't refresh.";
  const CHAT_STREAMING = "Omi is responding";
  const PHASE_TICK_LIMIT = 50;
  const MODE = window.__omiCAMode === "screen" ? "screen" : "full";

  const NAV_ROUTES = [
    "home",
    "conversations",
    "memories",
    "folders",
    "tasks",
    "rewind",
    "apps",
    "brain-map",
    "chat",
    "settings",
    "listen",
  ];

  const load = () => {
    try {
      const raw = sessionStorage.getItem(KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") return parsed;
    } catch { /* start fresh */ }
    return null;
  };

  const save = (state) => {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  };

  const fresh = () => ({
    phase: "boot",
    ticks: 0,
    phaseTicks: 0,
    steps: [],
    navIndex: 0,
    chatBaseline: null,
    sawStreaming: false,
    listenPermissionBefore: null,
    screenClicked: false,
    statusId: null,
  });

  const shell = () => document.querySelector("main[data-production-shell='true']");

  const routeOf = (root) => root?.getAttribute("data-route") ?? null;

  const visibleText = (root) => (root?.innerText || root?.textContent || "").replace(/\s+/g, " ").trim();

  const record = (state, slug, verdict) => {
    if (!state.steps.some((step) => step.slug === slug)) {
      state.steps.push({ slug, verdict });
    }
  };

  const finish = (state) => {
    state.phase = "done";
    save(state);
    return JSON.stringify({ schema: SCHEMA, steps: state.steps });
  };

  const timeout = (state, slug, verdict) => {
    record(state, slug, verdict);
    return false;
  };

  const channel = (name) => {
    const host = window;
    return host[name] ?? host.webkit?.messageHandlers?.[name] ?? null;
  };

  const inspectListen = () => {
    const ch = channel("omiListenSocket");
    if (ch == null || typeof ch.postMessage !== "function") return "channel-unreachable";
    return "present";
  };

  const click = (el) => {
    if (!el) return false;
    el.click();
    return true;
  };

  const nativeType = (textarea, value) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    if (!setter) return false;
    setter.call(textarea, value);
    textarea.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText" }));
    return true;
  };

  const navLink = (route) => {
    const nodes = document.querySelectorAll("a[href]");
    for (const node of nodes) {
      const href = node.getAttribute("href") || "";
      if (href.includes(`route=${route}`) && !node.closest(".command-palette")) return node;
    }
    return null;
  };

  const paletteButton = (label) => {
    const buttons = document.querySelectorAll(".command-palette-list button");
    for (const button of buttons) {
      const text = (button.textContent || "").replace(/\s+/g, " ").trim();
      if (text === label || text.startsWith(label)) return button;
    }
    return null;
  };

  const PALETTE_LABEL = {
    home: "Home",
    conversations: "Conversations",
    memories: "Memories",
    folders: "Folders",
    tasks: "Tasks",
    rewind: "Rewind",
    apps: "Apps",
    "brain-map": "Brain Map",
    chat: "Chat",
    settings: "Settings",
    listen: "Listen",
  };

  const requestRoute = (state, route) => {
    const link = navLink(route);
    if (link) {
      save(state);
      click(link);
      return "navigating";
    }
    const palette = document.querySelector(".command-palette");
    if (!palette) {
      const trigger = document.querySelector(".command-discovery-trigger");
      if (!trigger) return "missing-control";
      click(trigger);
      return "palette";
    }
    const button = paletteButton(PALETTE_LABEL[route] || route);
    if (!button || button.disabled) return "missing-control";
    save(state);
    click(button);
    return "navigating";
  };

  const installChatObserver = (state) => {
    if (window.__omiCAChatObserver) return;
    const root = shell() || document.body;
    const obs = new MutationObserver(() => {
      const current = load() || state;
      if (
        document.querySelector('.chat-message.is-assistant[data-delivery="streaming"]')
        || (document.body.innerText || "").includes(CHAT_STREAMING)
      ) {
        current.sawStreaming = true;
        save(current);
      }
    });
    obs.observe(root, { subtree: true, childList: true, attributes: true, characterData: true });
    window.__omiCAChatObserver = obs;
  };

  const assistantPersisted = () => {
    const nodes = document.querySelectorAll('.chat-message.is-assistant[data-delivery="canonical"] .chat-message-text');
    for (const node of nodes) {
      if ((node.textContent || "").trim().length > 0) return true;
    }
    return false;
  };

  let state = load() || fresh();
  if (state.phase === "done") return JSON.stringify({ schema: SCHEMA, steps: state.steps });

  const previousPhase = state.phase;
  state.ticks += 1;
  state.phaseTicks = state.phase === previousPhase ? (state.phaseTicks || 0) + 1 : 1;

  const root = shell();

  if (state.phase === "boot") {
    if (!root) {
      save(state);
      return PENDING;
    }
    if (MODE === "screen") {
      const skip = [
        "home", "chat", "mic",
        "nav.home", "nav.conversations", "nav.memories", "nav.folders",
        "nav.tasks", "nav.apps", "nav.brain-map", "nav.chat",
        "nav.settings", "nav.listen",
      ];
      for (const slug of skip) record(state, slug, "skipped-not-requested");
      state.phase = "rewind-nav";
      save(state);
      return PENDING;
    }
    state.phase = "home-wait";
    save(state);
    return PENDING;
  }

  if (state.phaseTicks > PHASE_TICK_LIMIT) {
    if (state.phase.startsWith("home")) timeout(state, "home", "timeout");
    else if (state.phase.startsWith("chat")) timeout(state, "chat", "timeout");
    else if (state.phase.startsWith("listen")) timeout(state, "mic", "timeout");
    else if (state.phase.startsWith("rewind") || state.phase.startsWith("screen")) {
      timeout(state, "screen", "timeout");
    } else if (state.phase.startsWith("nav")) {
      const route = NAV_ROUTES[state.navIndex];
      if (route) timeout(state, `nav.${route}`, "timeout");
      state.navIndex += 1;
      state.phase = "nav-next";
      state.phaseTicks = 0;
      save(state);
      return PENDING;
    } else {
      return finish(state);
    }
    if (state.phase.startsWith("home")) state.phase = "chat-nav";
    else if (state.phase.startsWith("chat")) state.phase = "listen-nav";
    else if (state.phase.startsWith("listen")) state.phase = "rewind-nav";
    else if (state.phase.startsWith("rewind") || state.phase.startsWith("screen")) state.phase = "nav-next";
    state.phaseTicks = 0;
    save(state);
    return PENDING;
  }

  if (state.phase === "home-wait") {
    if (!root || routeOf(root) !== "home") {
      save(state);
      return PENDING;
    }
    const phase = root.getAttribute("data-surface-state");
    if (phase === "initial-loading" || phase === "refreshing") {
      save(state);
      return PENDING;
    }
    state.phase = "home-assert";
    save(state);
    return PENDING;
  }

  if (state.phase === "home-assert") {
    const text = visibleText(root);
    const phase = root?.getAttribute("data-surface-state");
    if (!text.includes("Search saved Omi data") && !/items shown|matches/.test(text)) {
      record(state, "home", "not-rendered");
    } else if (text.includes(HOME_FAILURE_NOTICE) || phase === "saved-but-refresh-failed") {
      record(state, "home", "failure-notice");
    } else {
      record(state, "home", "ready");
    }
    record(state, "nav.home", routeOf(root) === "home" && visibleText(root).length > 0 ? "rendered" : "missing-surface");
    state.phase = "chat-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "chat-nav") {
    if (routeOf(root) === "chat") {
      state.phase = "chat-wait";
      save(state);
      return PENDING;
    }
    const entry = document.querySelector("a.home-chat-entry") || navLink("chat");
    if (entry) {
      save(state);
      click(entry);
      state.phase = "chat-wait";
      save(state);
      return PENDING;
    }
    const asked = requestRoute(state, "chat");
    if (asked === "navigating" || asked === "palette") {
      state.phase = asked === "palette" ? "chat-nav" : "chat-wait";
      save(state);
      return PENDING;
    }
    record(state, "chat", "no-control");
    record(state, "nav.chat", "missing-control");
    state.phase = "listen-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "chat-wait") {
    if (!root || routeOf(root) !== "chat") {
      save(state);
      return PENDING;
    }
    if (root.getAttribute("data-surface-state") !== "ready") {
      save(state);
      return PENDING;
    }
    record(state, "nav.chat", "rendered");
    state.phase = "chat-author";
    save(state);
    return PENDING;
  }

  if (state.phase === "chat-author") {
    const draft = document.querySelector("textarea.chat-draft");
    const send = document.querySelector("button.chat-send");
    if (!draft || !send) {
      record(state, "chat", "no-control");
      state.phase = "listen-nav";
      save(state);
      return PENDING;
    }
    state.chatBaseline = Number(root.getAttribute("data-consumer-chat-admission-count") || "0");
    if (!nativeType(draft, "control-acceptance ping")) {
      record(state, "chat", "send-failed");
      state.phase = "listen-nav";
      save(state);
      return PENDING;
    }
    state.phase = "chat-send";
    save(state);
    return PENDING;
  }

  if (state.phase === "chat-send") {
    const send = document.querySelector("button.chat-send");
    if (!send || send.disabled) {
      save(state);
      return PENDING;
    }
    installChatObserver(state);
    click(send);
    state.phase = "chat-wait-result";
    save(state);
    return PENDING;
  }

  if (state.phase === "chat-wait-result") {
    const admitted = Number(root?.getAttribute("data-consumer-chat-admission-count") || "0");
    const streamingNow = Boolean(
      document.querySelector('.chat-message.is-assistant[data-delivery="streaming"]')
      || visibleText(root).includes(CHAT_STREAMING),
    );
    if (streamingNow) state.sawStreaming = true;
    const persisted = assistantPersisted() && Number.isFinite(state.chatBaseline) && admitted > state.chatBaseline;
    if (!persisted) {
      save(state);
      return PENDING;
    }
    if (!state.sawStreaming) {
      record(state, "chat", "no-stream");
    } else {
      record(state, "chat", "streamed-and-persisted");
    }
    state.phase = "listen-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "listen-nav") {
    if (routeOf(root) === "listen") {
      state.phase = "listen-wait";
      save(state);
      return PENDING;
    }
    const mic = document.querySelector('a.nav-icon-control[href*="route=listen"]') || navLink("listen");
    if (mic) {
      save(state);
      click(mic);
      state.phase = "listen-wait";
      save(state);
      return PENDING;
    }
    const asked = requestRoute(state, "listen");
    if (asked === "navigating" || asked === "palette") {
      if (asked !== "palette") state.phase = "listen-wait";
      save(state);
      return PENDING;
    }
    record(state, "mic", "no-control");
    record(state, "nav.listen", "missing-control");
    state.phase = "rewind-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "listen-wait") {
    if (!root || routeOf(root) !== "listen") {
      save(state);
      return PENDING;
    }
    if (root.getAttribute("data-surface-state") === "initial-loading") {
      save(state);
      return PENDING;
    }
    record(state, "nav.listen", visibleText(root).length > 0 ? "rendered" : "missing-surface");
    state.phase = "listen-act";
    save(state);
    return PENDING;
  }

  if (state.phase === "listen-act") {
    if (inspectListen() === "channel-unreachable") {
      const allow = document.querySelector("button.listen-recovery-control");
      const start = document.querySelector("[data-consumer-action='start-listen']");
      click(allow || start);
      record(state, "mic", "channel-unreachable");
      state.phase = "rewind-nav";
      save(state);
      return PENDING;
    }
    const permission = document.querySelector("[data-permission-state]")?.getAttribute("data-permission-state");
    const allow = [...document.querySelectorAll("button.listen-recovery-control")].find((button) =>
      /Allow microphone|Open Settings/i.test(button.textContent || ""),
    );
    const start = document.querySelector("[data-consumer-action='start-listen']");
    if (permission === "denied" || /Open Settings/i.test(allow?.textContent || "")) {
      record(state, "mic", "skipped-tcc-denied");
      state.phase = "rewind-nav";
      save(state);
      return PENDING;
    }
    if (permission === "granted" && start && !start.disabled) {
      click(start);
      record(state, "mic", "skipped-already-granted");
      state.phase = "rewind-nav";
      save(state);
      return PENDING;
    }
    if (allow && /Allow microphone/i.test(allow.textContent || "")) {
      state.listenPermissionBefore = permission;
      click(allow);
      state.phase = "listen-wait-os";
      save(state);
      return PENDING;
    }
    if (start) {
      click(start);
      if (start.disabled) record(state, "mic", "no-control");
      else record(state, "mic", "skipped-already-granted");
      state.phase = "rewind-nav";
      save(state);
      return PENDING;
    }
    record(state, "mic", "no-control");
    state.phase = "rewind-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "listen-wait-os") {
    const permission = document.querySelector("[data-permission-state]")?.getAttribute("data-permission-state");
    // "checking" means the shell asked the OS. Do not wait for grant/deny —
    // the TCC prompt is host state this harness cannot click.
    if (permission === "checking") {
      record(state, "mic", "reached-os");
      state.phase = "rewind-nav";
      save(state);
      return PENDING;
    }
    if (permission === state.listenPermissionBefore) {
      save(state);
      return PENDING;
    }
    record(state, "mic", "reached-os");
    state.phase = "rewind-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "rewind-nav") {
    if (routeOf(root) === "rewind") {
      state.phase = "rewind-wait";
      save(state);
      return PENDING;
    }
    const link = navLink("rewind");
    if (link) {
      save(state);
      click(link);
      state.phase = "rewind-wait";
      save(state);
      return PENDING;
    }
    const asked = requestRoute(state, "rewind");
    if (asked === "navigating" || asked === "palette") {
      if (asked !== "palette") state.phase = "rewind-wait";
      save(state);
      return PENDING;
    }
    record(state, "screen", "no-control");
    record(state, "nav.rewind", "missing-control");
    state.phase = "nav-next";
    save(state);
    return PENDING;
  }

  if (state.phase === "rewind-wait") {
    if (!root || routeOf(root) !== "rewind") {
      save(state);
      return PENDING;
    }
    record(state, "nav.rewind", visibleText(root).length > 0 && /Rewind/.test(visibleText(root)) ? "rendered" : "missing-surface");
    state.phase = "rewind-click";
    save(state);
    return PENDING;
  }

  if (state.phase === "rewind-click") {
    const toggle = document.querySelector("button.screen-capture-toggle");
    const disabled = document.querySelector(".screen-capture-unavailable .production-disabled-control, .screen-capture-unavailable [role='button']");
    const permission = document.querySelector("button.screen-permission-action");
    click(toggle || permission || disabled);
    state.screenClicked = true;
    state.phase = "screen-status";
    save(state);
    return PENDING;
  }

  if (state.phase === "screen-status") {
    const screenChannel = channel("omiScreenBridge");
    if (screenChannel == null || typeof screenChannel.postMessage !== "function") {
      record(state, "screen", "bridge-unreachable");
      state.phase = "nav-next";
      save(state);
      return PENDING;
    }
    const id = `ca-status-${state.ticks}`;
    state.statusId = id;
    window.__omiCAScreenStatus = undefined;
    const previous = window.__omiScreenBridgeEvent;
    window.__omiScreenBridgeEvent = (replyId, event) => {
      if (typeof previous === "function") previous(replyId, event);
      if (replyId === id) window.__omiCAScreenStatus = event ?? true;
    };
    try {
      screenChannel.postMessage(JSON.stringify({ id, action: "screen.status", params: {} }));
    } catch {
      record(state, "screen", "bridge-unreachable");
      state.phase = "nav-next";
      save(state);
      return PENDING;
    }
    state.phase = "screen-status-wait";
    save(state);
    return PENDING;
  }

  if (state.phase === "screen-status-wait") {
    if (window.__omiCAScreenStatus === undefined) {
      save(state);
      return PENDING;
    }
    const permission = root?.getAttribute("data-permission");
    if (permission === "denied") record(state, "screen", "skipped-tcc-denied");
    else record(state, "screen", "reached-os");
    state.phase = "nav-next";
    save(state);
    return PENDING;
  }

  if (state.phase === "nav-next") {
    while (state.navIndex < NAV_ROUTES.length) {
      const route = NAV_ROUTES[state.navIndex];
      const slug = `nav.${route}`;
      if (state.steps.some((step) => step.slug === slug)) {
        state.navIndex += 1;
        continue;
      }
      if (routeOf(root) === route && visibleText(root).length > 0) {
        record(state, slug, "rendered");
        state.navIndex += 1;
        continue;
      }
      const asked = requestRoute(state, route);
      if (asked === "palette") {
        save(state);
        return PENDING;
      }
      if (asked === "missing-control") {
        record(state, slug, "missing-control");
        state.navIndex += 1;
        continue;
      }
      state.phase = "nav-wait";
      save(state);
      return PENDING;
    }
    return finish(state);
  }

  if (state.phase === "nav-wait") {
    const route = NAV_ROUTES[state.navIndex];
    const slug = `nav.${route}`;
    if (!root) {
      save(state);
      return PENDING;
    }
    if (routeOf(root) !== route) {
      save(state);
      return PENDING;
    }
    const text = visibleText(root);
    if (text.length === 0) {
      save(state);
      return PENDING;
    }
    record(state, slug, "rendered");
    state.navIndex += 1;
    state.phase = "nav-next";
    save(state);
    return PENDING;
  }

  save(state);
  return PENDING;
})()
