import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FocusRing: React.FC<{ progress: number }> = ({ progress }) => {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - progress);

  return (
    <svg width="110" height="110" viewBox="0 0 110 110">
      {/* Background circle */}
      <circle
        cx="55"
        cy="55"
        r={radius}
        fill="none"
        stroke="rgba(99, 102, 241, 0.15)"
        strokeWidth="6"
      />
      {/* Progress circle */}
      <circle
        cx="55"
        cy="55"
        r={radius}
        fill="none"
        stroke="#6366f1"
        strokeWidth="6"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={strokeDashoffset}
        transform="rotate(-90 55 55)"
        style={{ filter: "drop-shadow(0 0 8px rgba(99, 102, 241, 0.4))" }}
      />
    </svg>
  );
};

const TimelineBlock: React.FC<{
  label: string;
  duration: string;
  color: string;
  width: number;
  delay: number;
}> = ({ label, duration, color, width, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({ frame, fps, delay, config: { damping: 200 } });
  const barWidth = interpolate(entrance, [0, 1], [0, width]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ color: "#d1d5db", fontSize: 9 }}>{label}</span>
        <span style={{ color: "#6b7280", fontSize: 8 }}>{duration}</span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 3,
          background: "rgba(255,255,255,0.05)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${barWidth}%`,
            borderRadius: 3,
            background: `linear-gradient(90deg, ${color}, ${color}aa)`,
          }}
        />
      </div>
    </div>
  );
};

export const FocusScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const contentOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Animated focus percentage
  const focusPercent = Math.floor(
    interpolate(frame, [0.5 * fps, 2 * fps], [0, 87], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  const ringProgress = interpolate(frame, [0.5 * fps, 2 * fps], [0, 0.87], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Status badge
  const statusOpacity = interpolate(frame, [2.2 * fps, 2.5 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const statusScale = spring({
    frame,
    fps,
    delay: Math.round(2.2 * fps),
    config: { damping: 12 },
  });

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%)",
        fontFamily: "Inter, sans-serif",
      }}
    >
      {/* Section label */}
      <div
        style={{
          position: "absolute",
          top: 20,
          left: 30,
          display: "flex",
          alignItems: "center",
          gap: 6,
          opacity: contentOpacity,
        }}
      >
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#22c55e",
            boxShadow: "0 0 8px rgba(34, 197, 94, 0.5)",
          }}
        />
        <span style={{ color: "#6366f1", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>
          Focus Tracking
        </span>
      </div>

      <div style={{ display: "flex", height: "100%", alignItems: "center", padding: "0 30px", gap: 30, marginTop: 10 }}>
        {/* Left - Focus ring */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 10,
            opacity: contentOpacity,
          }}
        >
          <div style={{ position: "relative" }}>
            <FocusRing progress={ringProgress} />
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span style={{ color: "white", fontSize: 26, fontWeight: 800 }}>{focusPercent}%</span>
              <span style={{ color: "#a1a1aa", fontSize: 9 }}>focused</span>
            </div>
          </div>

          {/* Status badge */}
          <div
            style={{
              opacity: statusOpacity,
              transform: `scale(${statusScale})`,
              background: "rgba(34, 197, 94, 0.15)",
              border: "1px solid rgba(34, 197, 94, 0.3)",
              borderRadius: 14,
              padding: "4px 12px",
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
          >
            <div
              style={{
                width: 5,
                height: 5,
                borderRadius: "50%",
                background: "#22c55e",
                boxShadow: "0 0 6px rgba(34, 197, 94, 0.6)",
              }}
            />
            <span style={{ color: "#22c55e", fontSize: 9, fontWeight: 600 }}>Deep Focus Mode</span>
          </div>

          <h2 style={{ color: "white", fontSize: 18, fontWeight: 800, margin: 0, textAlign: "center" }}>
            Stay in the zone
          </h2>
        </div>

        {/* Right - Timeline & stats */}
        <div
          style={{
            flex: 1.2,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            opacity: contentOpacity,
          }}
        >
          <p style={{ color: "#a1a1aa", fontSize: 10, lineHeight: 1.6, margin: 0 }}>
            Omi detects when you're distracted and gently nudges you back. Track your focus streaks and understand your productivity patterns.
          </p>

          {/* Activity timeline */}
          <div
            style={{
              background: "rgba(30, 30, 46, 0.8)",
              borderRadius: 10,
              padding: 12,
              border: "1px solid rgba(99, 102, 241, 0.1)",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ color: "#6b7280", fontSize: 9, fontWeight: 600, textTransform: "uppercase", letterSpacing: 1 }}>
              Today's Activity
            </div>
            <TimelineBlock label="Deep Work — VS Code" duration="2h 15m" color="#6366f1" width={85} delay={Math.round(1 * fps)} />
            <TimelineBlock label="Meetings" duration="1h 30m" color="#f59e0b" width={55} delay={Math.round(1.3 * fps)} />
            <TimelineBlock label="Email & Slack" duration="45m" color="#ef4444" width={30} delay={Math.round(1.6 * fps)} />
            <TimelineBlock label="Break" duration="20m" color="#22c55e" width={15} delay={Math.round(1.9 * fps)} />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
