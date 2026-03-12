import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const NotificationCard: React.FC<{
  icon: string;
  title: string;
  body: string;
  delay: number;
  accent: string;
}> = ({ icon, title, body, delay, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const slideIn = spring({
    frame,
    fps,
    delay,
    config: { damping: 15, stiffness: 120 },
  });
  const x = interpolate(slideIn, [0, 1], [400, 0]);
  const opacity = interpolate(slideIn, [0, 1], [0, 1]);

  return (
    <div
      style={{
        opacity,
        transform: `translateX(${x}px)`,
        background: "rgba(30, 30, 46, 0.95)",
        borderRadius: 10,
        padding: 10,
        border: `1px solid ${accent}33`,
        boxShadow: `0 4px 16px rgba(0,0,0,0.3), 0 0 10px ${accent}15`,
        display: "flex",
        gap: 8,
        alignItems: "flex-start",
        maxWidth: 280,
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: 8,
          background: `${accent}20`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 14,
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ color: accent, fontSize: 7, fontWeight: 600, marginBottom: 1, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Omi Suggestion
        </div>
        <div style={{ color: "white", fontSize: 10, fontWeight: 600, marginBottom: 2 }}>{title}</div>
        <div style={{ color: "#9ca3af", fontSize: 9, lineHeight: 1.4 }}>{body}</div>
      </div>
    </div>
  );
};

export const ProactiveAdviceScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const headerY = interpolate(
    spring({ frame, fps, config: { damping: 200 } }),
    [0, 1],
    [20, 0]
  );

  // Background brain visualization
  const brainPulse = Math.sin(frame * 0.08) * 0.15 + 0.85;

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%)",
        fontFamily: "Inter, sans-serif",
      }}
    >
      {/* Background glow */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "30%",
          width: 200,
          height: 200,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(99, 102, 241, 0.08), transparent)",
          transform: `translate(-50%, -50%) scale(${brainPulse})`,
        }}
      />

      {/* Section label */}
      <div
        style={{
          position: "absolute",
          top: 20,
          left: 30,
          display: "flex",
          alignItems: "center",
          gap: 6,
          opacity: headerOpacity,
        }}
      >
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#a78bfa",
            boxShadow: "0 0 8px rgba(167, 139, 250, 0.5)",
          }}
        />
        <span style={{ color: "#6366f1", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>
          Proactive Advice
        </span>
      </div>

      <div style={{ display: "flex", height: "100%", alignItems: "center", padding: "0 30px", gap: 24, marginTop: 10 }}>
        {/* Left side - Header */}
        <div
          style={{
            flex: 1,
            opacity: headerOpacity,
            transform: `translateY(${headerY}px)`,
          }}
        >
          <h2
            style={{
              color: "white",
              fontSize: 22,
              fontWeight: 800,
              margin: 0,
              lineHeight: 1.2,
              letterSpacing: -0.5,
            }}
          >
            AI that thinks
            <br />
            <span style={{ color: "#a78bfa" }}>ahead of you</span>
          </h2>
          <p style={{ color: "#a1a1aa", fontSize: 10, lineHeight: 1.6, marginTop: 8, maxWidth: 220 }}>
            Based on your screen and conversations, Omi proactively surfaces tips, reminders, and insights — right when you need them.
          </p>
        </div>

        {/* Right side - Notification stack */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            alignItems: "flex-end",
          }}
        >
          <NotificationCard
            icon="💡"
            title="Add try-catch to processData"
            body="You have a TODO comment about error handling. The function could throw on invalid input."
            delay={Math.round(0.5 * fps)}
            accent="#6366f1"
          />
          <NotificationCard
            icon="📅"
            title="Standup in 5 minutes"
            body="Sarah mentioned the onboarding update — you may want to prepare your demo notes."
            delay={Math.round(1.2 * fps)}
            accent="#f59e0b"
          />
          <NotificationCard
            icon="🎯"
            title="Focus streak: 45 min"
            body="Great deep work session! Consider a short break to maintain productivity."
            delay={Math.round(1.9 * fps)}
            accent="#22c55e"
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
