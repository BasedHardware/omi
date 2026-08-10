import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { FIXTURE_STATES as MEMORY_STATES } from "../production/memory-fixtures.js";
import { CONVERSATION_FIXTURE_STATES } from "../production/conversation-fixtures.js";
import { FIXTURE_STATES as TASK_STATES } from "../production/task-fixtures.js";
import { PROPOSITION_FIXTURE_STATES } from "../production/proposition-fixtures.js";
import { CHAT_FIXTURE_STATES } from "../production/chat-fixtures.js";
import { SETTINGS_FIXTURE_STATES } from "../production/settings-fixtures.js";
import "./surface-lab.css";

type SurfaceId = "memories" | "memories-platform" | "conversations" | "conversation-detail" | "tasks" | "chat" | "settings";
type PreviewMode = "mobile" | "desktop" | "compare";

type SurfaceDefinition = {
  id: SurfaceId;
  label: string;
  description: string;
  states: readonly string[];
};

const SURFACES: readonly SurfaceDefinition[] = [
  { id: "memories", label: "Memories", description: "Saved context, editing, provenance, and sync recovery", states: MEMORY_STATES },
  { id: "conversations", label: "Conversations", description: "Library rows, filters, locks, and discarded records", states: CONVERSATION_FIXTURE_STATES },
  { id: "conversation-detail", label: "Conversation detail", description: "Selected-row summary, organization, and visibility", states: CONVERSATION_FIXTURE_STATES },
  { id: "tasks", label: "Tasks", description: "Today, Tomorrow, Later, keyboard flow, and queue recovery", states: TASK_STATES },
  // The platform generation is a separate record class, not the legacy surface with
  // fields hidden — propositions with lineage, no editing, honest recall completeness.
  { id: "memories-platform", label: "Memories (platform)", description: "Synthesized propositions, lineage, and honest recall completeness", states: PROPOSITION_FIXTURE_STATES },
  { id: "chat", label: "Chat", description: "Server-authoritative mirror, streaming, echo reconcile, and attachment cap", states: CHAT_FIXTURE_STATES },
  { id: "settings", label: "Settings", description: "Identity, appearance, and the entitlement upsell", states: SETTINGS_FIXTURE_STATES },
];

function selectedSurface(value: string | null): SurfaceDefinition {
  return SURFACES.find((surface) => surface.id === value) ?? SURFACES[0]!;
}

function selectedMode(value: string | null): PreviewMode {
  return value === "mobile" || value === "desktop" || value === "compare" ? value : "compare";
}

function fixtureHref(surface: SurfaceDefinition, state: string, platform: "mobile" | "desktop", locale: string): string {
  const params = new URLSearchParams({ qa: surface.id, state, platform, locale });
  return `?${params.toString()}`;
}

function Preview({ surface, state, platform, locale }: {
  surface: SurfaceDefinition;
  state: string;
  platform: "mobile" | "desktop";
  locale: string;
}): React.JSX.Element {
  const href = fixtureHref(surface, state, platform, locale);
  return (
    <article className={`surface-lab-preview surface-lab-preview-${platform}`}>
      <header>
        <div>
          <strong>{platform === "mobile" ? "390 × 844" : "Desktop"}</strong>
          <span>{surface.label} · {state}</span>
        </div>
        <a href={href} target="_blank" rel="noreferrer">Open</a>
      </header>
      <div className="surface-lab-frame-wrap">
        <iframe key={href} src={href} title={`${surface.label}, ${state}, ${platform}`} />
      </div>
    </article>
  );
}

function SurfaceLab(): React.JSX.Element {
  const initial = useMemo(() => new URLSearchParams(location.search), []);
  const [surface, setSurface] = useState(() => selectedSurface(initial.get("surface")));
  const [state, setState] = useState(() => {
    const requested = initial.get("state");
    const selected = selectedSurface(initial.get("surface"));
    return requested && selected.states.includes(requested) ? requested : "normal";
  });
  const [mode, setMode] = useState<PreviewMode>(() => selectedMode(initial.get("mode")));
  const [locale, setLocale] = useState(() => initial.get("locale")?.trim() || "en-US");

  const updateAddress = (nextSurface: SurfaceDefinition, nextState: string, nextMode: PreviewMode, nextLocale: string): void => {
    const params = new URLSearchParams({ lab: "1", surface: nextSurface.id, state: nextState, mode: nextMode, locale: nextLocale });
    history.replaceState(null, "", `?${params.toString()}`);
  };

  const chooseSurface = (nextSurface: SurfaceDefinition): void => {
    const nextState = nextSurface.states.includes(state) ? state : "normal";
    setSurface(nextSurface);
    setState(nextState);
    updateAddress(nextSurface, nextState, mode, locale);
  };
  const chooseState = (nextState: string): void => {
    setState(nextState);
    updateAddress(surface, nextState, mode, locale);
  };
  const chooseMode = (nextMode: PreviewMode): void => {
    setMode(nextMode);
    updateAddress(surface, state, nextMode, locale);
  };
  const chooseLocale = (nextLocale: string): void => {
    setLocale(nextLocale);
    updateAddress(surface, state, mode, nextLocale);
  };

  return (
    <main className="surface-lab">
      <header className="surface-lab-hero">
        <div>
          <p className="surface-lab-kicker">Self-contained frontend QA</p>
          <h1>Omi Surface Lab</h1>
          <p>Every production surface and deterministic state, without a backend or native build.</p>
        </div>
      </header>

      <section className="surface-lab-controls" aria-label="Preview controls">
        <div className="surface-lab-surface-tabs" role="tablist" aria-label="Surface">
          {SURFACES.map((item) => (
            <button key={item.id} type="button" role="tab" aria-selected={item.id === surface.id} onClick={() => chooseSurface(item)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="surface-lab-control-row">
          <div className="surface-lab-mode" aria-label="Viewport">
            {(["mobile", "desktop", "compare"] as const).map((item) => (
              <button key={item} type="button" aria-pressed={mode === item} onClick={() => chooseMode(item)}>{item}</button>
            ))}
          </div>
          <label>
            Locale
            <input value={locale} onChange={(event) => chooseLocale(event.target.value || "en-US")} spellCheck="false" />
          </label>
        </div>
      </section>

      <section className="surface-lab-state-panel">
        <div>
          <h2>{surface.label}</h2>
          <p>{surface.description}</p>
        </div>
        <div className="surface-lab-states" aria-label={`${surface.label} fixture state`}>
          {surface.states.map((item) => (
            <button key={item} type="button" aria-pressed={state === item} onClick={() => chooseState(item)}>{item}</button>
          ))}
        </div>
      </section>

      <section className={`surface-lab-previews surface-lab-previews-${mode}`} aria-live="polite">
        {mode !== "desktop" && <Preview surface={surface} state={state} platform="mobile" locale={locale} />}
        {mode !== "mobile" && <Preview surface={surface} state={state} platform="desktop" locale={locale} />}
      </section>
    </main>
  );
}

document.documentElement.dataset["surfaceLab"] = "true";
document.title = "Omi Surface Lab";
createRoot(document.getElementById("root")!).render(<StrictMode><SurfaceLab /></StrictMode>);
