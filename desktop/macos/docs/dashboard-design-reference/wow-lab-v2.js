const states = {
  recommendation: {
    icon: "clipboard-check",
    eyebrow: "What matters now",
    title: "Finalize Q3 launch checklist",
    context: "Homepage QA sign-off is still missing — plus 2 more items, due Wednesday.",
    action: "Assign owners",
    actionFeedback: "Opening the Q3 launch checklist.",
    more: [
      { eyebrow: "Earlier today", title: "Send retro summary to the team", context: "From your standup notes this morning." },
      { eyebrow: "Yesterday", title: "Review Priya's scope doc", context: "Flagged in the roadmap session — still open." }
    ]
  },
  recent: {
    icon: "message-circle",
    eyebrow: "Continue where you left off",
    title: "Product sync — standup notes",
    context: "Lena owns the pricing comparison — plus 2 more items from this conversation.",
    action: "Open conversation",
    actionFeedback: "Opening Product sync — standup notes.",
    more: [
      { eyebrow: "2 days ago", title: "Design review — onboarding flow", context: "3 open comments, last touched Tuesday." },
      { eyebrow: "Last week", title: "Q3 roadmap planning session", context: "Action items extracted, 1 still unassigned." }
    ]
  },
  "day-zero": {
    eyebrow: "Here's what Omi can already do",
    cards: [
      {
        icon: "monitor",
        text: "You're in Linear — “Bug: Auth token refresh loop.” Ask Omi to summarize it or draft a fix plan.",
        action: "Ask about this",
        actionFeedback: "Asking about your current screen."
      },
      {
        icon: "calendar",
        text: "Design sync at 2pm today, from your connected calendar. Omi can prep notes before it starts.",
        action: "Prep notes",
        actionFeedback: "Prepping notes for Design sync."
      },
      {
        icon: "file-text",
        text: "Your “Q3 Roadmap” doc in Notion is connected. Ask Omi anything from it, right now.",
        action: "Ask about it",
        actionFeedback: "Asking about the Q3 Roadmap doc."
      }
    ]
  }
};

const heroIcons = {
  "clipboard-check": `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect width="8" height="4" x="8" y="2" rx="1" ry="1"></rect>
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
      <path d="m9 14 2 2 4-4"></path>
    </svg>`,
  "message-circle": `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
    </svg>`,
  monitor: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect width="20" height="14" x="2" y="3" rx="2"></rect>
      <line x1="8" y1="21" x2="16" y2="21"></line>
      <line x1="12" y1="17" x2="12" y2="21"></line>
    </svg>`,
  calendar: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
      <line x1="16" y1="2" x2="16" y2="6"></line>
      <line x1="8" y1="2" x2="8" y2="6"></line>
      <line x1="3" y1="10" x2="21" y2="10"></line>
    </svg>`,
  "file-text": `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
      <line x1="16" y1="13" x2="8" y2="13"></line>
      <line x1="16" y1="17" x2="8" y2="17"></line>
      <polyline points="10 9 9 9 8 9"></polyline>
    </svg>`
};

const connectors = [
  { id: "notion", name: "Notion", detail: "Project notes and docs", connected: true },
  { id: "calendar", name: "Google Calendar", detail: "Meetings and routines", connected: true },
  { id: "gmail", name: "Gmail", detail: "Email history and follow-ups", connected: false, action: "Connect" },
  { id: "files", name: "Local files", detail: "Documents, code, and folders", connected: false, action: "Choose folders" }
];

const featureSettings = [
  { id: "voice-shortcut", title: "Voice shortcut", detail: "Hold to ask Omi from anywhere", value: "⌘ O" },
  { id: "floating-bar", title: "Show floating bar", detail: "Keep Ask Omi available over other apps", enabled: true },
  { id: "reduce-transparency", title: "Reduce transparency", detail: "Use solid surfaces instead of glass", enabled: false }
];

const scene = document.getElementById("v2Scene");
const toast = document.getElementById("v2Toast");
const pages = document.getElementById("v2Pages");
const connectContent = document.getElementById("v2ConnectContent");
const featuresContent = document.getElementById("v2FeaturesContent");
const tierButtons = [...document.querySelectorAll("[data-tier]")];
const pageTabButtons = [...document.querySelectorAll("[data-page-tab]")];
const pageOrder = ["home", "connect", "features"];

let currentState = "recommendation";
let dayZeroCardIndex = 0;
let dayZeroPaused = false;
let dayZeroRotationTimer;
let dayZeroTransitionTimer;
let transitionTimer;
let toastTimer;
let pageSyncFrame;
const dayZeroRotationDelay = 5000;

function escapeText(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function heroActionMarkup(data) {
  return `
    <div class="v2-action-row">
      <button class="v2-action" type="button" data-action-feedback="${escapeText(data.actionFeedback)}">
        <span>${escapeText(data.action)}</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <line x1="5" y1="12" x2="19" y2="12"></line>
          <polyline points="12 5 19 12 12 19"></polyline>
        </svg>
      </button>
    </div>`;
}

function dayZeroCardMarkup(card) {
  return `
    <div class="v2-day-zero-moment">
      <span class="v2-moment-icon">${heroIcons[card.icon]}</span>
      <p class="v2-day-zero-text">${escapeText(card.text)}</p>
    </div>
    ${heroActionMarkup(card)}`;
}

function dayZeroMarkup(data) {
  return `
    <article class="v2-proof-card v2-day-zero-proof">
      <p class="v2-eyebrow">${escapeText(data.eyebrow)}</p>
      <div class="v2-day-zero-stage" data-day-zero-stage>
        ${dayZeroCardMarkup(data.cards[dayZeroCardIndex])}
      </div>
      <div class="v2-day-zero-dots" role="group" aria-label="Choose a day-zero example">
        ${data.cards.map((_, index) => `
          <button
            class="v2-day-zero-dot"
            type="button"
            data-day-zero-card="${index}"
            aria-label="Show example ${index + 1} of ${data.cards.length}"
            aria-pressed="${index === dayZeroCardIndex}"
          ><span aria-hidden="true"></span></button>`).join("")}
      </div>
    </article>`;
}

function moreDrawerMarkup(items) {
  return `
    <div class="v2-more-drawer" aria-label="More items" data-more-drawer>
      <button class="v2-more-toggle" type="button" data-more-toggle aria-expanded="false">
        <span>More</span>
        <svg class="v2-more-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"></polyline></svg>
      </button>
      <ul class="v2-more-list" data-more-list hidden>
        ${items.map(item => `
          <li class="v2-more-item">
            <p class="v2-eyebrow">${escapeText(item.eyebrow)}</p>
            <p class="v2-more-title">${escapeText(item.title)}</p>
            <p class="v2-more-context">${escapeText(item.context)}</p>
          </li>`).join('')}
      </ul>
    </div>`;
}

function stateMarkup(data) {
  if (data.cards) return dayZeroMarkup(data);

  return `
    <article class="v2-proof-card">
      <div class="v2-card-kicker">
        <span class="v2-moment-icon">${heroIcons[data.icon]}</span>
        <p class="v2-eyebrow">${escapeText(data.eyebrow)}</p>
      </div>
      <h1 class="v2-title">${escapeText(data.title)}</h1>
      <p class="v2-context">${escapeText(data.context)}</p>
      <div class="v2-action-row">
        <button class="v2-action" type="button" data-action-feedback="${escapeText(data.actionFeedback)}">
          <span>${escapeText(data.action)}</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="5" y1="12" x2="19" y2="12"></line>
            <polyline points="12 5 19 12 12 19"></polyline>
          </svg>
        </button>
      </div>
      ${data.more ? moreDrawerMarkup(data.more) : ''}
    </article>`;
}

function updateDayZeroDots() {
  scene.querySelectorAll("[data-day-zero-card]").forEach(button => {
    button.setAttribute("aria-pressed", String(Number(button.dataset.dayZeroCard) === dayZeroCardIndex));
  });
}

function renderDayZeroCard({ animate = false } = {}) {
  const stage = scene.querySelector("[data-day-zero-stage]");
  if (!stage) return;
  clearTimeout(dayZeroTransitionTimer);

  const updateStage = () => {
    stage.innerHTML = dayZeroCardMarkup(states["day-zero"].cards[dayZeroCardIndex]);
    updateDayZeroDots();
  };

  if (!animate) {
    updateStage();
    return;
  }

  stage.classList.add("is-leaving");
  dayZeroTransitionTimer = setTimeout(() => {
    updateStage();
    stage.classList.remove("is-leaving");
    stage.classList.add("is-entering");
    requestAnimationFrame(() => requestAnimationFrame(() => stage.classList.remove("is-entering")));
  }, 130);
}

function scheduleDayZeroRotation() {
  clearTimeout(dayZeroRotationTimer);
  if (currentState !== "day-zero" || dayZeroPaused) return;

  dayZeroRotationTimer = setTimeout(() => {
    dayZeroCardIndex = (dayZeroCardIndex + 1) % states["day-zero"].cards.length;
    renderDayZeroCard({ animate: true });
    scheduleDayZeroRotation();
  }, dayZeroRotationDelay);
}

function syncDayZeroRotation() {
  clearTimeout(dayZeroRotationTimer);
  clearTimeout(dayZeroTransitionTimer);
  dayZeroPaused = false;
  if (currentState === "day-zero") scheduleDayZeroRotation();
}

function connectDataMarkup() {
  return `
    <div class="v2-destination-intro">
      <h2>Connect the places where you work.</h2>
      <p>Omi uses this context for memories, tasks, and answers.</p>
    </div>
    <div class="v2-connector-list">
      ${connectors.map(connector => `
        <article class="v2-connector-row">
          <div class="v2-connector-mark" aria-hidden="true">${escapeText(connector.name.at(0))}</div>
          <div class="v2-connector-copy">
            <h3>${escapeText(connector.name)}</h3>
            <p>${escapeText(connector.detail)}</p>
          </div>
          <button
            class="v2-connector-action${connector.connected ? " is-connected" : ""}"
            type="button"
            data-connector-id="${escapeText(connector.id)}"
            ${connector.connected ? "disabled" : ""}
          >${connector.connected ? "Connected" : escapeText(connector.action)}</button>
        </article>`).join("")}
    </div>`;
}

function featureSettingsMarkup() {
  return `
    <div class="v2-destination-intro">
      <h2>Everyday controls, close at hand.</h2>
      <p>Advanced account and privacy options stay in Settings.</p>
    </div>
    <div class="v2-settings-list">
      ${featureSettings.map(setting => `
        <div class="v2-setting-row">
          <div>
            <h3>${escapeText(setting.title)}</h3>
            <p>${escapeText(setting.detail)}</p>
          </div>
          ${setting.value
            ? `<button class="v2-setting-value" type="button" data-shortcut-setting>${escapeText(setting.value)}</button>`
            : `<button
                class="v2-setting-toggle"
                type="button"
                role="switch"
                aria-checked="${setting.enabled}"
                aria-label="${escapeText(setting.title)}"
                data-setting-toggle="${escapeText(setting.id)}"
                data-setting-label="${escapeText(setting.title)}"
              ><span aria-hidden="true"></span></button>`}
        </div>`).join("")}
    </div>`;
}

function renderDestinationPages() {
  connectContent.innerHTML = connectDataMarkup();
  featuresContent.innerHTML = featureSettingsMarkup();
}

function updatePageTabs(page) {
  pageTabButtons.forEach(button => {
    button.setAttribute("aria-selected", String(button.dataset.pageTab === page));
  });
}

function showPage(page) {
  const pageIndex = Math.max(0, pageOrder.indexOf(page));
  const left = pages.clientWidth * pageIndex;
  const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  updatePageTabs(pageOrder[pageIndex]);
  pages.scrollTo({ left, behavior });
}

function updateControls() {
  tierButtons.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.tier === currentState)));
  history.replaceState(null, "", `#${currentState}`);
}

function skeletonMarkup() {
  return `
    <article class="v2-proof-card v2-skeleton-card" aria-hidden="true">
      <div class="v2-skeleton-kicker">
        <div class="v2-skeleton v2-skeleton-icon"></div>
        <div class="v2-skeleton v2-skeleton-eyebrow"></div>
      </div>
      <div class="v2-skeleton v2-skeleton-title"></div>
      <div class="v2-skeleton v2-skeleton-title v2-skeleton-title--short"></div>
      <div class="v2-skeleton v2-skeleton-context"></div>
      <div class="v2-skeleton v2-skeleton-context v2-skeleton-context--short"></div>
      <div class="v2-skeleton v2-skeleton-action"></div>
    </article>`;
}

function render({ animate = false, skipSkeleton = false } = {}) {
  clearTimeout(transitionTimer);
  if (currentState !== "day-zero") {
    clearTimeout(dayZeroRotationTimer);
    clearTimeout(dayZeroTransitionTimer);
  }

  if (!animate && !skipSkeleton) {
    // Show skeleton briefly to simulate async cascade settle
    scene.innerHTML = skeletonMarkup();
    transitionTimer = setTimeout(() => {
      scene.classList.add("is-entering");
      scene.innerHTML = stateMarkup(states[currentState]);
      updateControls();
      syncDayZeroRotation();
      requestAnimationFrame(() => requestAnimationFrame(() => scene.classList.remove("is-entering")));
    }, 420);
    updateControls();
    return;
  }

  if (!animate) {
    scene.innerHTML = stateMarkup(states[currentState]);
    updateControls();
    syncDayZeroRotation();
    return;
  }

  scene.classList.add("is-leaving");
  transitionTimer = setTimeout(() => {
    scene.innerHTML = stateMarkup(states[currentState]);
    updateControls();
    syncDayZeroRotation();
    scene.classList.remove("is-leaving");
    scene.classList.add("is-entering");
    requestAnimationFrame(() => requestAnimationFrame(() => scene.classList.remove("is-entering")));
  }, 130);
}

function showToast(message) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("is-visible");
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2200);
}

tierButtons.forEach(button => {
  button.addEventListener("click", () => {
    if (currentState === button.dataset.tier) return;
    if (button.dataset.tier === "day-zero") dayZeroCardIndex = 0;
    currentState = button.dataset.tier;
    render({ animate: true });
  });
});

pageTabButtons.forEach(button => {
  button.addEventListener("click", () => showPage(button.dataset.pageTab));
});

pages.addEventListener("scroll", () => {
  cancelAnimationFrame(pageSyncFrame);
  pageSyncFrame = requestAnimationFrame(() => {
    const pageIndex = Math.min(pageOrder.length - 1, Math.max(0, Math.round(pages.scrollLeft / pages.clientWidth)));
    updatePageTabs(pageOrder[pageIndex]);
  });
});

document.querySelector(".v2-settings")?.addEventListener("click", () => showPage("features"));

connectContent.addEventListener("click", event => {
  const connectorButton = event.target.closest("[data-connector-id]");
  if (!connectorButton) return;
  const connector = connectors.find(item => item.id === connectorButton.dataset.connectorId);
  if (!connector) return;
  if (connector.id === "files") {
    showToast("Opening folder picker.");
    return;
  }
  connector.connected = true;
  renderDestinationPages();
  showToast(`${connector.name} connected.`);
});

featuresContent.addEventListener("click", event => {
  const toggle = event.target.closest("[data-setting-toggle]");
  if (toggle) {
    const setting = featureSettings.find(item => item.id === toggle.dataset.settingToggle);
    if (!setting) return;
    setting.enabled = !setting.enabled;
    renderDestinationPages();
    showToast(`${toggle.dataset.settingLabel} turned ${setting.enabled ? "on" : "off"}.`);
    return;
  }

  if (event.target.closest("[data-shortcut-setting]")) showToast("Opening voice shortcut settings.");
});

document.querySelectorAll("[data-task]").forEach(button => {
  button.addEventListener("click", () => {
    const completed = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", String(completed));
    button.closest("li").classList.toggle("is-complete", completed);
    showToast(completed ? "Task completed." : "Task reopened.");
  });
});

document.querySelector("[data-view-tasks]")?.addEventListener("click", () => {
  showToast("Opening Tasks.");
});

// Composer submit
const composerForm = document.getElementById("v2Composer");
const composerInput = document.getElementById("v2ComposerInput");
if (composerForm && composerInput) {
  composerForm.addEventListener("submit", event => {
    event.preventDefault();
    const query = composerInput.value.trim();
    if (!query) return;
    showToast(`Asking Omi: "${query.length > 60 ? query.slice(0, 60) + "…" : query}"`);
    composerInput.value = "";
    composerInput.blur();
  });
}

scene.addEventListener("click", event => {
  const dayZeroDot = event.target.closest("[data-day-zero-card]");
  if (dayZeroDot) {
    const nextIndex = Number(dayZeroDot.dataset.dayZeroCard);
    clearTimeout(dayZeroRotationTimer);
    if (nextIndex !== dayZeroCardIndex) {
      dayZeroCardIndex = nextIndex;
      renderDayZeroCard({ animate: true });
    }
    scheduleDayZeroRotation();
    return;
  }

  const moreToggle = event.target.closest("[data-more-toggle]");
  if (moreToggle) {
    const list = moreToggle.closest("[data-more-drawer]").querySelector("[data-more-list]");
    const expanded = moreToggle.getAttribute("aria-expanded") === "true";
    moreToggle.setAttribute("aria-expanded", String(!expanded));
    moreToggle.classList.toggle("is-open", !expanded);
    if (expanded) {
      list.setAttribute("hidden", "");
    } else {
      list.removeAttribute("hidden");
    }
    return;
  }

  const action = event.target.closest("[data-action-feedback]");
  if (action) showToast(action.dataset.actionFeedback);

});

scene.addEventListener("mouseenter", () => {
  if (currentState !== "day-zero") return;
  dayZeroPaused = true;
  clearTimeout(dayZeroRotationTimer);
});

scene.addEventListener("mouseleave", () => {
  if (currentState !== "day-zero") return;
  dayZeroPaused = false;
  scheduleDayZeroRotation();
});

document.addEventListener("keydown", event => {
  if (event.target.matches("input, textarea, [contenteditable='true']")) return;
  if (event.key === "Escape" && pages.scrollLeft > 0) {
    showPage("home");
    return;
  }
  const keyMap = { "1": "recommendation", "2": "recent", "3": "day-zero" };
  if (!keyMap[event.key]) return;
  if (keyMap[event.key] === "day-zero") dayZeroCardIndex = 0;
  currentState = keyMap[event.key];
  render({ animate: true });
});

const hashState = location.hash.slice(1);
if (states[hashState]) currentState = hashState;

render();
renderDestinationPages();
updatePageTabs("home");
