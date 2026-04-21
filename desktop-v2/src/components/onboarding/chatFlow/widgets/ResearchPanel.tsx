import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Package,
  Code2,
  LayoutGrid,
  Globe,
  Building2,
  Zap,
} from "lucide-react";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Badge } from "@/components/ui/badge";
import { useAuthStore } from "@/stores/authStore";
import { useOnboardingStore } from "@/stores/onboardingStore";
import { useOnboardingCompanionStore } from "@/stores/onboardingCompanionStore";
import type { WidgetResult } from "../types";

interface Props {
  disabled: boolean;
  onCapture: (result: WidgetResult, summary: string | null) => void;
}

interface ScanSnapshot {
  file_count: number;
  project_names: string[];
  applications: string[];
  technologies: string[];
  complete: boolean;
  current_root: string | null;
}

interface WebResearchOutcome {
  summary: string;
  results: { query: string; title: string; url: string; snippet: string }[];
}

interface ResearchSession {
  promise: Promise<WebResearchOutcome | null>;
  outcome: WebResearchOutcome | null;
  projectNames: string[];
  applications: string[];
  technologies: string[];
  orgHint: string | null;
  subscribers: Set<() => void>;
}
let activeResearch: ResearchSession | null = null;

async function runResearch(
  preferredName: string,
  email: string | null,
): Promise<ResearchSession> {
  if (activeResearch) return activeResearch;
  const session: ResearchSession = {
    promise: Promise.resolve(null),
    outcome: null,
    projectNames: [],
    applications: [],
    technologies: [],
    orgHint: null,
    subscribers: new Set(),
  };
  activeResearch = session;

  const notify = () => session.subscribers.forEach((fn) => fn());

  session.promise = (async () => {
    // File scan snapshot (scan ran on earlier step)
    try {
      const snap = await invoke<ScanSnapshot>("get_file_scan_status");
      session.projectNames = snap.project_names ?? [];
      session.applications = snap.applications ?? [];
      session.technologies = snap.technologies ?? [];
      useOnboardingCompanionStore.getState().updateSignals({
        projectNames: session.projectNames,
        applications: session.applications,
        technologies: session.technologies,
      });
      notify();
    } catch {
      // scan unavailable — continue with empty signals
    }

    // Organization hint
    try {
      const hint = await invoke<string | null>(
        "onboarding_organization_hint",
        { email: email ?? null },
      );
      session.orgHint = hint ?? null;
      useOnboardingCompanionStore
        .getState()
        .updateSignals({ orgHint: session.orgHint });
      notify();
    } catch {
      /* ignore */
    }

    // Gemini grounded research
    try {
      const outcome = await Promise.race<WebResearchOutcome>([
        invoke<WebResearchOutcome>("gemini_onboarding_research", {
          preferredName: preferredName || "",
          email: email ?? null,
          projectNames: session.projectNames,
          applications: session.applications,
          technologies: session.technologies,
        }),
        new Promise<WebResearchOutcome>((_, reject) =>
          window.setTimeout(
            () => reject(new Error("invoke-timeout-45s")),
            45_000,
          ),
        ),
      ]);
      session.outcome = outcome;
      if (outcome?.summary) {
        useOnboardingCompanionStore
          .getState()
          .updateSignals({ webSummary: outcome.summary });
      }
      notify();
      return outcome;
    } catch (err) {
      console.warn("[research] gemini failed:", err);
      return null;
    }
  })();

  return session;
}

export function ResearchPanelWidget({ disabled, onCapture }: Props) {
  const userEmail = useAuthStore((s) => s.userEmail);
  const preferredName = useOnboardingStore((s) => s.preferredName);
  const [session, setSession] = useState<ResearchSession | null>(null);
  const [, forceRender] = useState(0);
  const capturedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    void runResearch(preferredName, userEmail).then((s) => {
      if (!cancelled) setSession(s);
    });
    return () => {
      cancelled = true;
    };
  }, [preferredName, userEmail]);

  useEffect(() => {
    if (!session) return;
    const rerender = () => forceRender((n) => n + 1);
    session.subscribers.add(rerender);
    return () => {
      session.subscribers.delete(rerender);
    };
  }, [session]);

  useEffect(() => {
    if (!session || disabled || capturedRef.current) return;
    void session.promise.then(() => {
      if (capturedRef.current) return;
      capturedRef.current = true;
      const summary =
        session.outcome?.summary?.slice(0, 120) ?? "Second brain ready";
      onCapture({ scanDone: true }, summary);
    });
  }, [session, disabled, onCapture]);

  if (!session) {
    return (
      <div className="mt-2">
        <Shimmer>Getting to know you…</Shimmer>
      </div>
    );
  }

  const cards: { icon: React.ReactNode; title: string; detail: string }[] = [];
  if (session.projectNames.length > 0) {
    cards.push({
      icon: <Package size={14} />,
      title: "From your machine",
      detail: session.projectNames.slice(0, 3).join(", "),
    });
  }
  if (session.technologies.length > 0) {
    cards.push({
      icon: <Code2 size={14} />,
      title: "Your stack",
      detail: session.technologies.slice(0, 5).join(", "),
    });
  }
  if (session.applications.length > 0) {
    cards.push({
      icon: <LayoutGrid size={14} />,
      title: "Apps you use",
      detail: session.applications.slice(0, 6).join(", "),
    });
  }
  if (session.outcome?.summary) {
    cards.push({
      icon: <Globe size={14} />,
      title: "From the web",
      detail: session.outcome.summary,
    });
  } else if (!session.outcome && !capturedRef.current) {
    cards.push({
      icon: <Zap size={14} />,
      title: "Searching the web",
      detail: "Grounding your context with Gemini + Google Search.",
    });
  } else if (session.orgHint) {
    cards.push({
      icon: <Building2 size={14} />,
      title: "Identity hint",
      detail: session.orgHint,
    });
  }

  return (
    <div className="flex flex-col gap-2 mt-2">
      {cards.map((card, i) => (
        <div
          key={i}
          className="flex items-start gap-3 rounded-lg border border-border/50 bg-muted/30 p-3"
        >
          <div className="h-7 w-7 shrink-0 rounded-md bg-muted/50 flex items-center justify-center text-muted-foreground">
            {card.icon}
          </div>
          <div className="flex flex-col gap-0.5 min-w-0">
            <div className="text-[13px] font-semibold text-foreground">
              {card.title}
            </div>
            <div className="text-[12px] text-muted-foreground leading-relaxed">
              {card.detail}
            </div>
          </div>
        </div>
      ))}
      {!session.outcome ? <Shimmer>Still thinking…</Shimmer> : null}
      {session.outcome?.results && session.outcome.results.length > 0 ? (
        <div className="flex items-center gap-1.5 flex-wrap">
          {session.outcome.results.slice(0, 4).map((r, i) => (
            <Badge
              key={i}
              variant="secondary"
              className="bg-muted/50 text-muted-foreground border-border/50 text-[11px]"
            >
              {r.title.slice(0, 32)}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}
