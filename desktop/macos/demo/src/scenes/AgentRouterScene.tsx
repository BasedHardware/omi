import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type RouterSceneMode = "route" | "setup" | "fallback";

type RouterSceneProps = {
  badge: string;
  headline: string;
  body: string;
  query: string;
  routeLabel: string;
  routeSubtext: string;
  mode: RouterSceneMode;
  accent: string;
  secondaryAccent: string;
  pillLabels: string[];
  calloutTitle: string;
  calloutBody: string;
};

const ShellCard: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      background: "rgba(15, 23, 42, 0.92)",
      border: "1px solid rgba(255, 255, 255, 0.08)",
      borderRadius: 20,
      boxShadow: "0 24px 60px rgba(0, 0, 0, 0.35)",
      overflow: "hidden",
    }}
  >
    {children}
  </div>
);

const WindowChrome: React.FC<{ title: string }> = ({ title }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "12px 16px",
      borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
      background: "rgba(255, 255, 255, 0.02)",
    }}
  >
    <div style={{ display: "flex", gap: 6 }}>
      <div style={{ width: 10, height: 10, borderRadius: 999, background: "#ef4444" }} />
      <div style={{ width: 10, height: 10, borderRadius: 999, background: "#f59e0b" }} />
      <div style={{ width: 10, height: 10, borderRadius: 999, background: "#22c55e" }} />
    </div>
    <div style={{ flex: 1, textAlign: "center", color: "#d1d5db", fontSize: 11, fontWeight: 600 }}>
      {title}
    </div>
  </div>
);

const Pill: React.FC<{ label: string; tone: string; subtle?: boolean }> = ({ label, tone, subtle }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 8,
      padding: "7px 12px",
      borderRadius: 999,
      background: subtle ? "rgba(255,255,255,0.04)" : `${tone}18`,
      border: `1px solid ${tone}55`,
      color: subtle ? "#cbd5e1" : tone,
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: 0.2,
      whiteSpace: "nowrap",
    }}
  >
    <span style={{ width: 7, height: 7, borderRadius: 999, background: tone, flexShrink: 0 }} />
    {label}
  </div>
);

const ListItem: React.FC<{ index: number; title: string; detail: string; tone: string }> = ({
  index,
  title,
  detail,
  tone,
}) => (
  <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
    <div
      style={{
        width: 22,
        height: 22,
        borderRadius: 999,
        background: `${tone}1f`,
        border: `1px solid ${tone}55`,
        color: tone,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 11,
        fontWeight: 800,
        flexShrink: 0,
      }}
    >
      {index}
    </div>
    <div style={{ minWidth: 0 }}>
      <div style={{ color: "#f8fafc", fontSize: 13, fontWeight: 700 }}>{title}</div>
      <div style={{ color: "#94a3b8", fontSize: 11, lineHeight: 1.45, marginTop: 2 }}>{detail}</div>
    </div>
  </div>
);

const QueryBar: React.FC<{
  query: string;
  frame: number;
  typeStart: number;
  typeEnd: number;
  tone: string;
}> = ({ query, frame, typeStart, typeEnd, tone }) => {
  const charCount = Math.floor(
    interpolate(frame, [typeStart, typeEnd], [0, query.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const visible = query.slice(0, charCount);
  const cursorVisible = Math.sin(frame * 0.25) > 0 && charCount < query.length;

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.05)",
        border: `1px solid ${tone}55`,
        borderRadius: 16,
        padding: "14px 16px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        boxShadow: `0 0 24px ${tone}18`,
      }}
    >
      <div
        style={{
          width: 18,
          height: 18,
          borderRadius: 999,
          border: `2px solid ${tone}`,
          position: "relative",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            position: "absolute",
            width: 8,
            height: 2,
            background: tone,
            right: -5,
            bottom: -1,
            transform: "rotate(45deg)",
            borderRadius: 999,
          }}
        />
      </div>
      <div style={{ color: "#f8fafc", fontSize: 15, fontWeight: 600, letterSpacing: 0.1 }}>
        {visible}
        {cursorVisible && <span style={{ color: tone }}>|</span>}
      </div>
    </div>
  );
};

const RouterScene: React.FC<RouterSceneProps> = ({
  badge,
  headline,
  body,
  query,
  routeLabel,
  routeSubtext,
  mode,
  accent,
  secondaryAccent,
  pillLabels,
  calloutTitle,
  calloutBody,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const labelOpacity = interpolate(frame, [0, 0.25 * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const titleY = interpolate(spring({ frame, fps, config: { damping: 180 } }), [0, 1], [16, 0]);
  const introOpacity = interpolate(frame, [0.2 * fps, 0.9 * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const panelScale = interpolate(spring({ frame, fps, config: { damping: 180 } }), [0, 1], [0.98, 1]);
  const routePulse = 0.9 + Math.sin(frame * 0.12) * 0.03;

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at top left, rgba(34, 211, 238, 0.12), transparent 28%), radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.1), transparent 25%), linear-gradient(135deg, #05070b 0%, #0f172a 54%, #05070b 100%)",
        fontFamily: "Inter, system-ui, sans-serif",
        padding: 28,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 18,
          left: 28,
          display: "flex",
          alignItems: "center",
          gap: 8,
          opacity: labelOpacity,
        }}
      >
        <div style={{ width: 7, height: 7, borderRadius: 999, background: accent, boxShadow: `0 0 10px ${accent}77` }} />
        <span style={{ color: accent, fontSize: 10, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase" }}>
          {badge}
        </span>
      </div>

      <div style={{ display: "flex", gap: 24, height: "100%", alignItems: "center", marginTop: 10 }}>
        <div
          style={{
            flex: 1.18,
            display: "flex",
            flexDirection: "column",
            gap: 18,
            opacity: introOpacity,
            transform: `translateY(${titleY}px) scale(${panelScale})`,
          }}
        >
          <div>
            <h1 style={{ color: "#f8fafc", fontSize: 28, lineHeight: 1.08, margin: 0, fontWeight: 800 }}>
              {headline}
            </h1>
            <p style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.6, margin: "10px 0 0", maxWidth: 360 }}>
              {body}
            </p>
          </div>

          <QueryBar query={query} frame={frame} typeStart={0.4 * fps} typeEnd={1.6 * fps} tone={accent} />

          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {pillLabels.map((pill, i) => (
              <div
                key={pill}
                style={{
                  opacity: interpolate(frame, [1.1 * fps + i * 5, 1.1 * fps + i * 5 + 6], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  }),
                }}
              >
                <Pill label={pill} tone={i % 2 === 0 ? accent : secondaryAccent} subtle={i % 2 === 1} />
              </div>
            ))}
          </div>
        </div>

        <div style={{ flex: 0.92, display: "flex", justifyContent: "center" }}>
          <ShellCard>
            <WindowChrome title="Ask Omi" />
            <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <div>
                  <div style={{ color: "#94a3b8", fontSize: 10, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>
                    Routing result
                  </div>
                  <div style={{ color: "#f8fafc", fontSize: 18, fontWeight: 800, marginTop: 4 }}>{routeLabel}</div>
                </div>
                <div style={{ transform: `scale(${routePulse})` }}>
                  <Pill label={routeLabel} tone={accent} />
                </div>
              </div>

              <div
                style={{
                  color: "#cbd5e1",
                  fontSize: 12,
                  lineHeight: 1.6,
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 14,
                  padding: 14,
                }}
              >
                {routeSubtext}
              </div>

              {mode === "route" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <ListItem index={1} title="Explicit mention wins" detail="The user named Codex directly, so the router selects it before defaulting to Claude Code." tone={accent} />
                  <ListItem index={2} title="Availability still matters" detail="The router only chooses an agent that is actually connected." tone={secondaryAccent} />
                  <ListItem index={3} title="Best fit, no guesswork" detail="The task goes to the agent that matches the request and is ready to run." tone={accent} />
                </div>
              )}

              {mode === "setup" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <ListItem index={1} title="Install Codex CLI" detail="Add the command-line agent to your PATH so Omi can launch it." tone={accent} />
                  <ListItem index={2} title="Set your API key" detail="Provide OPENAI_API_KEY, then relaunch Omi to detect the provider." tone={secondaryAccent} />
                  <ListItem index={3} title="Try again" detail="When Codex is connected, the same spoken command routes straight through." tone={accent} />
                </div>
              )}

              {mode === "fallback" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div
                    style={{
                      padding: 12,
                      borderRadius: 14,
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid rgba(255,255,255,0.08)",
                    }}
                  >
                    <div style={{ color: "#f8fafc", fontSize: 12, fontWeight: 800 }}>First attempt</div>
                    <div style={{ color: "#94a3b8", fontSize: 11, marginTop: 3 }}>Codex starts, then throws a retryable run failure.</div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "center", color: secondaryAccent, fontSize: 18, fontWeight: 900 }}>
                    ↓ fallback
                  </div>
                  <div
                    style={{
                      padding: 12,
                      borderRadius: 14,
                      background: `${secondaryAccent}12`,
                      border: `1px solid ${secondaryAccent}55`,
                    }}
                  >
                    <div style={{ color: "#f8fafc", fontSize: 12, fontWeight: 800 }}>Next available agent</div>
                    <div style={{ color: "#cbd5e1", fontSize: 11, marginTop: 3 }}>
                      The plan advances automatically, so the task keeps moving instead of dying silently.
                    </div>
                  </div>
                </div>
              )}

              <div
                style={{
                  marginTop: 4,
                  borderRadius: 14,
                  padding: 14,
                  background: `${secondaryAccent}12`,
                  border: `1px solid ${secondaryAccent}44`,
                }}
              >
                <div style={{ color: secondaryAccent, fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: 1.1 }}>
                  {calloutTitle}
                </div>
                <div style={{ color: "#e2e8f0", fontSize: 12, lineHeight: 1.55, marginTop: 4 }}>
                  {calloutBody}
                </div>
              </div>
            </div>
          </ShellCard>
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const AgentRouterRouteScene: React.FC = () => (
  <RouterScene
    badge="Agent Router"
    headline={"Route every task to the right agent."}
    body="When the user says Codex, Omi routes directly to it instead of guessing. The router still respects whether the agent is actually available."
    query="codex: patch the retry fallback"
    routeLabel="Codex"
    routeSubtext="The spoken request names Codex, so the router picks it ahead of the default path."
    mode="route"
    accent="#22d3ee"
    secondaryAccent="#34d399"
    pillLabels={["explicit mention", "availability check", "best available agent"]}
    calloutTitle="Why it matters"
    calloutBody="No silent failure, no surprise fallback, and no guessing when the user already asked for a specific coding agent."
  />
);

export const AgentRouterSetupScene: React.FC = () => (
  <RouterScene
    badge="Not connected"
    headline="Guide setup instead of silently falling back."
    body="If a named agent is missing, Omi should tell the user exactly what to install and how to connect it."
    query="codex: fix the failing dispatch"
    routeLabel="Codex needs setup"
    routeSubtext="The router sees the provider request, but the provider isn't installed yet — so it shows setup guidance instead of switching agents behind the scenes."
    mode="setup"
    accent="#f59e0b"
    secondaryAccent="#fb7185"
    pillLabels={["install the CLI", "set OPENAI_API_KEY", "try again"]}
    calloutTitle="Guided install"
    calloutBody="The app surfaces a clear setup path: install the agent, add credentials, and then rerun the same request."
  />
);

export const AgentRouterFallbackScene: React.FC = () => (
  <RouterScene
    badge="Retry fallback"
    headline="Keep going when one run fails."
    body="If the first execution fails in a retryable way, the plan advances to the next available agent instead of surfacing a dead end."
    query="codex: run the test fix again"
    routeLabel="Fallback to Claude Code"
    routeSubtext="Codex starts, hits a retryable run failure, and the fallback executor advances the plan without losing the task."
    mode="fallback"
    accent="#34d399"
    secondaryAccent="#22c55e"
    pillLabels={["retryable failure", "next available agent", "structured final error"]}
    calloutTitle="Reliable handoff"
    calloutBody="The final failure is still surfaced if every option is exhausted, but non-final failures never leak a terminal error to the user."
  />
);
