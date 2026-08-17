(() => {
  const PENDING = "OMI_CONTROL_PENDING";
  const SCHEMA = "omi.control-acceptance.v1";
  const KEY = "omi.control-acceptance.v1";
  const HOME_FAILURE_NOTICE = "Showing saved data. Couldn't refresh.";
  const CHAT_STREAMING = "Omi is responding";
  const JOURNEY_CHAT_PROMPT = "journey-acceptance ping";
  const PHASE_TICK_LIMIT = 50;
  // Stated outcome deadline. The macOS probe hook caps attempts at 250, so a
  // longer wait here starves Chat/Rewind/nav when Listen does not transcribe.
  const OUTCOME_TICK_LIMIT = 40;
  // Real-model chat wait. GLM-4.7 spent 34s in a reasoning preamble on the
  // journey hop; 50 ticks × 0.4s = 20s timed out while the provider was still
  // thinking. 160 × 0.4s = 64s covers the 60s first-content liveness bound.
  const REAL_CHAT_TICK_LIMIT = 160;
  const MODE = window.__omiCAMode === "screen"
    ? "screen"
    : window.__omiCAMode === "journey"
      ? "journey"
      : "full";
  const REAL = window.__omiCAReal === true;
  const BASELINE = window.__omiCABaseline && typeof window.__omiCABaseline === "object"
    ? window.__omiCABaseline
    : { conversationIds: [], memoryIds: [] };

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
    screenFrameSelected: false,
    statusId: null,
    witnesses: null,
    transcriptNeedles: [],
    conversationId: null,
    memoryId: null,
    memoryText: null,
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
    const payload = { schema: SCHEMA, steps: state.steps };
    if (state.witnesses) payload.witnesses = state.witnesses;
    return JSON.stringify(payload);
  };

  const onRoute = (root, route) => {
    const current = routeOf(root);
    if (route === "rewind") return current === "rewind" || current === "screen";
    return current === route;
  };

  const phaseLimit = (phase) => {
    if (phase === "chat-wait-result" || phase === "journey-chat-wait-result") {
      return REAL ? REAL_CHAT_TICK_LIMIT : PHASE_TICK_LIMIT;
    }
    if (
      phase === "listen-wait-transcript"
      || phase === "screen-wait-outcome"
      || phase === "listen-stop"
      || phase === "conversations-wait"
      || phase === "memories-wait"
      || phase === "home-memory-wait"
    ) return OUTCOME_TICK_LIMIT;
    return PHASE_TICK_LIMIT;
  };

  const JOURNEY_SLUGS = ["mic", "conversation", "memory", "home.memory", "chat.memory"];

  const blockRest = (state, fromSlug) => {
    let seen = false;
    for (const slug of JOURNEY_SLUGS) {
      if (slug === fromSlug) seen = true;
      else if (seen) record(state, slug, "blocked-prior");
    }
  };

  const afterListen = (state, ok) => {
    if (MODE !== "journey") {
      state.phase = "rewind-nav";
      return "continue";
    }
    if (ok) {
      state.phase = "listen-stop";
      return "continue";
    }
    blockRest(state, "mic");
    return "finish";
  };

  const listenTranscript = (root) => {
    const semantic = root?.getAttribute("data-consumer-semantic") || "";
    const match = semantic.match(/^listen:capture:[^:]+:segments:(\d+)$/);
    const segments = match ? Number(match[1]) : 0;
    const transcript = (root?.getAttribute("data-consumer-transcript") || "").trim();
    const rows = root?.querySelectorAll(".listen-transcript-row") ?? [];
    let rowText = "";
    for (const row of rows) {
      const text = (row.querySelector(".listen-transcript-text")?.textContent || row.textContent || "").trim();
      if (text) rowText += (rowText ? " " : "") + text;
    }
    if (segments > 0 && transcript.length > 0 && rows.length > 0 && rowText.length > 0) {
      return "transcript-rendered";
    }
    return "empty-transcript";
  };

  const transcriptNeedlesOf = (root) => {
    const rows = root?.querySelectorAll(".listen-transcript-row") ?? [];
    const needles = [];
    for (const row of rows) {
      const text = (row.querySelector(".listen-transcript-text")?.textContent || row.textContent || "").trim();
      if (text) needles.push(text);
    }
    return needles;
  };

  const conversationRow = (baselineIds) => {
    const known = baselineIds || [];
    const nodes = document.querySelectorAll("[data-conversation-id]");
    for (const node of nodes) {
      const id = (node.getAttribute("data-conversation-id") || "").trim();
      if (id && known.indexOf(id) === -1) return { verdict: "row-rendered", id };
    }
    return { verdict: "row-missing", id: null };
  };

  const memoryCard = (baselineIds, needles) => {
    const known = baselineIds || [];
    const hay = needles || [];
    const nodes = document.querySelectorAll("[data-proposition-id]");
    for (const node of nodes) {
      const id = (node.getAttribute("data-proposition-id") || "").trim();
      if (!id || known.indexOf(id) !== -1) continue;
      const text = ((node.querySelector(".proposition-text")?.textContent || node.textContent || "")).replace(/\s+/g, " ").trim();
      for (let i = 0; i < hay.length; i += 1) {
        if (hay[i] && text.includes(hay[i])) return { verdict: "card-rendered", id, text };
      }
    }
    return { verdict: "card-missing", id: null, text: "" };
  };

  const homeMemoryRow = (memoryText) => {
    const needle = (memoryText || "").replace(/\s+/g, " ").trim();
    if (!needle) return "row-missing";
    const nodes = document.querySelectorAll(".home-result-row");
    for (const node of nodes) {
      const text = (node.textContent || "").replace(/\s+/g, " ").trim();
      if (text.includes(needle)) return "row-rendered";
    }
    return "row-missing";
  };

  const screenFrame = (root) => {
    if (root?.querySelector(".screen-frame-unavailable")) return "frame-unavailable";
    const img = root?.querySelector("img.screen-frame-image");
    if (!img) {
      if (root?.querySelector(".screen-frame-loading")) return "frame-loading";
      return "frame-missing";
    }
    const src = img.getAttribute("src") || "";
    if (!src.startsWith("data:image/png;base64,")) return "frame-not-png";
    if (src.slice("data:image/png;base64,".length).trim().length === 0) return "frame-empty-bytes";
    if (!Number.isFinite(img.naturalWidth) || img.naturalWidth <= 0) return "frame-undecoded";
    return "frame-rendered";
  };

  const selectTimelineFrame = () => {
    const timeline = document.querySelector(".screen-timeline input[type='range']");
    if (!timeline) return false;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (!setter) return false;
    setter.call(timeline, timeline.max || "0");
    timeline.dispatchEvent(new Event("input", { bubbles: true }));
    timeline.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  };

  const lastCanonicalAssistant = () => {
    const nodes = document.querySelectorAll('.chat-message.is-assistant[data-delivery="canonical"]');
    return nodes.length > 0 ? nodes[nodes.length - 1] : null;
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
  if (state.phase === "done") {
    const payload = { schema: SCHEMA, steps: state.steps };
    if (state.witnesses) payload.witnesses = state.witnesses;
    return JSON.stringify(payload);
  }

  const previousPhase = state.phase;
  state.ticks += 1;
  state.phaseTicks = state.phase === previousPhase ? (state.phaseTicks || 0) + 1 : 1;

  const root = shell();
  const chatWait = state.phase === "chat-wait-result" || state.phase === "journey-chat-wait-result";
  const streamingNow = Boolean(
    document.querySelector('.chat-message.is-assistant[data-delivery="streaming"]')
    || visibleText(root).includes(CHAT_STREAMING)
    || String(root?.getAttribute("data-consumer-semantic") || "").includes("streaming:1"),
  );
  if (chatWait && streamingNow) {
    // The assistant is still working. A tick budget sized for canned chat
    // must not fire while the real model is visibly thinking.
    state.sawStreaming = true;
    state.phaseTicks = 1;
  }

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
    if (MODE === "journey") {
      state.phase = "listen-nav";
      save(state);
      return PENDING;
    }
    state.phase = "home-wait";
    save(state);
    return PENDING;
  }

  if (state.phaseTicks > phaseLimit(state.phase)) {
    if (state.phase === "listen-wait-transcript") timeout(state, "mic", listenTranscript(root));
    else if (state.phase === "listen-act") timeout(state, "mic", "no-control");
    else if (state.phase === "listen-stop") timeout(state, "conversation", "stop-failed");
    else if (state.phase === "conversations-wait" || state.phase === "conversations-nav") {
      timeout(state, "conversation", conversationRow(BASELINE.conversationIds).verdict);
    }
    else if (state.phase === "memories-wait" || state.phase === "memories-nav") {
      timeout(state, "memory", memoryCard(BASELINE.memoryIds, state.transcriptNeedles).verdict);
    }
    else if (state.phase === "home-memory-wait" || state.phase === "home-memory-nav") {
      timeout(state, "home.memory", homeMemoryRow(state.memoryText));
    }
    else if (state.phase === "screen-wait-outcome" || state.phase === "screen-assert-frame") {
      timeout(state, "screen", screenFrame(root));
    }
    else if (state.phase.startsWith("home")) timeout(state, "home", "timeout");
    else if (state.phase.startsWith("chat") || state.phase.startsWith("journey-chat")) {
      state.witnesses = {
        ...(state.witnesses || {}),
        timeoutPhase: state.phase,
        timeoutTicks: state.phaseTicks,
        timeoutLimit: phaseLimit(state.phase),
        real: REAL,
      };
      timeout(state, MODE === "journey" ? "chat.memory" : "chat", "timeout");
    }
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
    if (MODE === "journey") {
      const last = state.steps[state.steps.length - 1];
      if (last) blockRest(state, last.slug);
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
    const assistant = lastCanonicalAssistant();
    const capabilityLabel = (assistant?.querySelector(".chat-agent-capability")?.textContent || "").trim();
    const assistantText = (assistant?.querySelector(".chat-message-text")?.textContent || "").trim();
    if (!capabilityLabel) {
      save(state);
      return PENDING;
    }
    state.witnesses = {
      ...(state.witnesses || {}),
      chat: { capabilityLabel, assistantText },
    };
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
    if (MODE !== "journey") record(state, "nav.listen", "missing-control");
    if (afterListen(state, false) === "finish") return finish(state);
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
    if (MODE !== "journey") {
      record(state, "nav.listen", visibleText(root).length > 0 ? "rendered" : "missing-surface");
    }
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
      if (afterListen(state, false) === "finish") return finish(state);
      save(state);
      return PENDING;
    }
    const permission = document.querySelector("[data-permission-state]")?.getAttribute("data-permission-state");
    const allow = [...document.querySelectorAll("button.listen-recovery-control")].find((button) =>
      /Allow microphone|Open Settings/i.test(button.textContent || ""),
    );
    const start = document.querySelector("[data-consumer-action='start-listen']");
    const capturing = root?.getAttribute("data-capture-kind") === "capturing";
    if (permission === "denied" || /Open Settings/i.test(allow?.textContent || "")) {
      record(state, "mic", "skipped-tcc-denied");
      if (afterListen(state, false) === "finish") return finish(state);
      save(state);
      return PENDING;
    }
    if (capturing) {
      state.phase = "listen-wait-transcript";
      save(state);
      return PENDING;
    }
    if (start && start.disabled) {
      save(state);
      return PENDING;
    }
    if (permission === "granted" && start) {
      click(start);
      state.phase = "listen-wait-transcript";
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
      state.phase = "listen-wait-transcript";
      save(state);
      return PENDING;
    }
    save(state);
    return PENDING;
  }

  if (state.phase === "listen-wait-os") {
    const permission = document.querySelector("[data-permission-state]")?.getAttribute("data-permission-state");
    // "checking" means the shell asked the OS. Do not treat that as a pass,
    // and do not wait for a grant the harness cannot click. Denied is the
    // only skip; anything else either proceeds to capture or times out.
    if (permission === "denied" || /Open Settings/i.test(
      [...document.querySelectorAll("button.listen-recovery-control")].find((button) =>
        /Open Settings/i.test(button.textContent || ""),
      )?.textContent || "",
    )) {
      record(state, "mic", "skipped-tcc-denied");
      if (afterListen(state, false) === "finish") return finish(state);
      save(state);
      return PENDING;
    }
    if (permission === "granted") {
      state.phase = "listen-act";
      save(state);
      return PENDING;
    }
    save(state);
    return PENDING;
  }

  if (state.phase === "listen-wait-transcript") {
    if (listenTranscript(root) === "transcript-rendered") {
      record(state, "mic", "transcript-rendered");
      state.transcriptNeedles = transcriptNeedlesOf(root);
      if (afterListen(state, true) === "finish") return finish(state);
      save(state);
      return PENDING;
    }
    save(state);
    return PENDING;
  }

  if (state.phase === "listen-stop") {
    const capturing = root?.getAttribute("data-capture-kind") === "capturing";
    if (!capturing) {
      state.phase = "conversations-nav";
      save(state);
      return PENDING;
    }
    const stop = document.querySelector("button.listen-stop-control");
    if (stop && !stop.disabled) click(stop);
    save(state);
    return PENDING;
  }

  if (state.phase === "conversations-nav") {
    if (routeOf(root) === "conversations") {
      state.phase = "conversations-wait";
      save(state);
      return PENDING;
    }
    const asked = requestRoute(state, "conversations");
    if (asked === "navigating" || asked === "palette") {
      if (asked !== "palette") state.phase = "conversations-wait";
      save(state);
      return PENDING;
    }
    record(state, "conversation", "no-control");
    blockRest(state, "conversation");
    return finish(state);
  }

  if (state.phase === "conversations-wait") {
    if (!root || routeOf(root) !== "conversations") {
      save(state);
      return PENDING;
    }
    const found = conversationRow(BASELINE.conversationIds);
    if (found.verdict !== "row-rendered") {
      save(state);
      return PENDING;
    }
    record(state, "conversation", "row-rendered");
    state.conversationId = found.id;
    state.witnesses = { ...(state.witnesses || {}), conversationId: found.id };
    state.phase = "memories-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "memories-nav") {
    if (routeOf(root) === "memories") {
      state.phase = "memories-wait";
      save(state);
      return PENDING;
    }
    const asked = requestRoute(state, "memories");
    if (asked === "navigating" || asked === "palette") {
      if (asked !== "palette") state.phase = "memories-wait";
      save(state);
      return PENDING;
    }
    record(state, "memory", "no-control");
    blockRest(state, "memory");
    return finish(state);
  }

  if (state.phase === "memories-wait") {
    if (!root || routeOf(root) !== "memories") {
      save(state);
      return PENDING;
    }
    const found = memoryCard(BASELINE.memoryIds, state.transcriptNeedles);
    if (found.verdict !== "card-rendered") {
      save(state);
      return PENDING;
    }
    record(state, "memory", "card-rendered");
    state.memoryId = found.id;
    state.memoryText = found.text;
    state.witnesses = {
      ...(state.witnesses || {}),
      memoryId: found.id,
      memoryText: found.text,
      transcriptNeedles: state.transcriptNeedles,
    };
    state.phase = "home-memory-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "home-memory-nav") {
    if (routeOf(root) === "home") {
      state.phase = "home-memory-wait";
      save(state);
      return PENDING;
    }
    const asked = requestRoute(state, "home");
    if (asked === "navigating" || asked === "palette") {
      if (asked !== "palette") state.phase = "home-memory-wait";
      save(state);
      return PENDING;
    }
    record(state, "home.memory", "no-control");
    blockRest(state, "home.memory");
    return finish(state);
  }

  if (state.phase === "home-memory-wait") {
    if (!root || routeOf(root) !== "home") {
      save(state);
      return PENDING;
    }
    const verdict = homeMemoryRow(state.memoryText);
    if (verdict !== "row-rendered") {
      save(state);
      return PENDING;
    }
    record(state, "home.memory", "row-rendered");
    state.phase = "journey-chat-nav";
    save(state);
    return PENDING;
  }

  if (state.phase === "journey-chat-nav") {
    if (routeOf(root) === "chat") {
      state.phase = "journey-chat-wait";
      save(state);
      return PENDING;
    }
    const entry = document.querySelector("a.home-chat-entry") || navLink("chat");
    if (entry) {
      save(state);
      click(entry);
      state.phase = "journey-chat-wait";
      save(state);
      return PENDING;
    }
    const asked = requestRoute(state, "chat");
    if (asked === "navigating" || asked === "palette") {
      state.phase = asked === "palette" ? "journey-chat-nav" : "journey-chat-wait";
      save(state);
      return PENDING;
    }
    record(state, "chat.memory", "no-control");
    return finish(state);
  }

  if (state.phase === "journey-chat-wait") {
    if (!root || routeOf(root) !== "chat") {
      save(state);
      return PENDING;
    }
    if (root.getAttribute("data-surface-state") !== "ready") {
      save(state);
      return PENDING;
    }
    state.phase = "journey-chat-author";
    save(state);
    return PENDING;
  }

  if (state.phase === "journey-chat-author") {
    const draft = document.querySelector("textarea.chat-draft");
    const send = document.querySelector("button.chat-send");
    if (!draft || !send) {
      record(state, "chat.memory", "no-control");
      return finish(state);
    }
    state.chatBaseline = Number(root.getAttribute("data-consumer-chat-admission-count") || "0");
    if (!nativeType(draft, JOURNEY_CHAT_PROMPT)) {
      record(state, "chat.memory", "send-failed");
      return finish(state);
    }
    state.phase = "journey-chat-send";
    save(state);
    return PENDING;
  }

  if (state.phase === "journey-chat-send") {
    const send = document.querySelector("button.chat-send");
    if (!send || send.disabled) {
      save(state);
      return PENDING;
    }
    installChatObserver(state);
    click(send);
    state.phase = "journey-chat-wait-result";
    save(state);
    return PENDING;
  }

  if (state.phase === "journey-chat-wait-result") {
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
    const assistant = lastCanonicalAssistant();
    const capabilityLabel = (assistant?.querySelector(".chat-agent-capability")?.textContent || "").trim();
    const assistantText = (assistant?.querySelector(".chat-message-text")?.textContent || "").trim();
    if (!capabilityLabel) {
      save(state);
      return PENDING;
    }
    state.witnesses = {
      ...(state.witnesses || {}),
      chat: { capabilityLabel, assistantText },
      memoryId: state.memoryId,
      conversationId: state.conversationId,
      memoryText: state.memoryText,
      transcriptNeedles: state.transcriptNeedles,
    };
    if (!state.sawStreaming) {
      record(state, "chat.memory", "no-stream");
    } else {
      record(state, "chat.memory", "streamed-and-persisted");
    }
    return finish(state);
  }

  if (state.phase === "rewind-nav") {
    if (onRoute(root, "rewind")) {
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
    if (!root || !onRoute(root, "rewind")) {
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
    if (permission === "denied") {
      record(state, "screen", "skipped-tcc-denied");
      state.phase = "nav-next";
      save(state);
      return PENDING;
    }
    state.phase = "screen-wait-outcome";
    save(state);
    return PENDING;
  }

  if (state.phase === "screen-wait-outcome") {
    const permission = root?.getAttribute("data-permission");
    if (permission === "denied") {
      record(state, "screen", "skipped-tcc-denied");
      state.phase = "nav-next";
      save(state);
      return PENDING;
    }
    const total = Number(root?.getAttribute("data-frame-total") || "0");
    if (Number.isFinite(total) && total > 0 && !state.screenFrameSelected) {
      state.screenFrameSelected = selectTimelineFrame();
    }
    const verdict = screenFrame(root);
    if (verdict === "frame-rendered") {
      record(state, "screen", "frame-rendered");
      state.phase = "nav-next";
      save(state);
      return PENDING;
    }
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
      if (onRoute(root, route) && visibleText(root).length > 0) {
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
    if (!onRoute(root, route)) {
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
