import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const TaskItem: React.FC<{
  text: string;
  source: string;
  priority: "high" | "medium" | "low";
  delay: number;
}> = ({ text, source, priority, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({
    frame,
    fps,
    delay,
    config: { damping: 15 },
  });
  const x = interpolate(entrance, [0, 1], [-50, 0]);
  const opacity = interpolate(entrance, [0, 1], [0, 1]);

  // Checkbox animation
  const checkDelay = delay + Math.round(0.6 * fps);
  const checkProgress = spring({
    frame,
    fps,
    delay: checkDelay,
    config: { damping: 12 },
  });

  const priorityColors = {
    high: "#ef4444",
    medium: "#f59e0b",
    low: "#22c55e",
  };

  return (
    <div
      style={{
        opacity,
        transform: `translateX(${x}px)`,
        background: "rgba(30, 30, 46, 0.8)",
        borderRadius: 8,
        padding: 10,
        border: "1px solid rgba(99, 102, 241, 0.1)",
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      {/* Checkbox */}
      <div
        style={{
          width: 16,
          height: 16,
          borderRadius: 4,
          border: `2px solid ${checkProgress > 0.5 ? "#6366f1" : "#4b5563"}`,
          background: checkProgress > 0.5 ? "#6366f1" : "transparent",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          transition: "none",
        }}
      >
        {checkProgress > 0.5 && (
          <span style={{ color: "white", fontSize: 10, fontWeight: 700 }}>✓</span>
        )}
      </div>

      <div style={{ flex: 1 }}>
        <div
          style={{
            color: checkProgress > 0.5 ? "#6b7280" : "white",
            fontSize: 10,
            fontWeight: 500,
            textDecoration: checkProgress > 0.5 ? "line-through" : "none",
          }}
        >
          {text}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 2 }}>
          <span style={{ color: "#6b7280", fontSize: 8 }}>from: {source}</span>
          <div
            style={{
              width: 4,
              height: 4,
              borderRadius: "50%",
              background: priorityColors[priority],
            }}
          />
          <span style={{ color: priorityColors[priority], fontSize: 8, fontWeight: 500 }}>{priority}</span>
        </div>
      </div>
    </div>
  );
};

export const TaskExtractionScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Animated connection lines
  const lineProgress = interpolate(frame, [0.3 * fps, 1.5 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
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
          opacity: headerOpacity,
        }}
      >
        <div
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#f59e0b",
            boxShadow: "0 0 8px rgba(245, 158, 11, 0.5)",
          }}
        />
        <span style={{ color: "#6366f1", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>
          Task Extraction
        </span>
      </div>

      <div style={{ display: "flex", height: "100%", alignItems: "center", padding: "0 30px", gap: 20, marginTop: 10 }}>
        {/* Conversation snippet */}
        <div
          style={{
            flex: 1,
            opacity: headerOpacity,
          }}
        >
          <h2 style={{ color: "white", fontSize: 20, fontWeight: 800, margin: 0, letterSpacing: -0.5, marginBottom: 10 }}>
            Conversations
            <br />
            <span style={{ color: "#f59e0b" }}>become tasks</span>
          </h2>

          {/* Conversation bubble */}
          <div
            style={{
              background: "rgba(30, 30, 46, 0.8)",
              borderRadius: 10,
              padding: 12,
              border: "1px solid rgba(99, 102, 241, 0.15)",
            }}
          >
            <div style={{ color: "#6b7280", fontSize: 8, marginBottom: 6 }}>Team Standup — 10:32 AM</div>
            <p style={{ color: "#d1d5db", fontSize: 9, lineHeight: 1.6, margin: 0 }}>
              "...so we need to <span style={{ color: "#f59e0b", fontWeight: 600 }}>update the API docs</span> before the release.
              Also, <span style={{ color: "#f59e0b", fontWeight: 600 }}>Mike should review the PR</span> by end of day, and
              someone needs to <span style={{ color: "#f59e0b", fontWeight: 600 }}>set up the staging environment</span> for QA."
            </p>
          </div>

          {/* Arrow / connection */}
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              padding: "6px 0",
              opacity: lineProgress,
            }}
          >
            <svg width="24" height="24" viewBox="0 0 40 40">
              <path
                d="M20 5 L20 30 M12 22 L20 30 L28 22"
                stroke="#6366f1"
                strokeWidth="2"
                fill="none"
                strokeDasharray={`${lineProgress * 50}`}
                strokeLinecap="round"
              />
            </svg>
          </div>
        </div>

        {/* Extracted tasks */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              color: "#6b7280",
              fontSize: 9,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: 1,
              marginBottom: 2,
              opacity: interpolate(frame, [0.8 * fps, 1 * fps], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          >
            Auto-extracted Tasks
          </div>

          <TaskItem
            text="Update API docs before release"
            source="Sarah, standup"
            priority="high"
            delay={Math.round(1 * fps)}
          />
          <TaskItem
            text="Review PR (assigned: Mike)"
            source="Sarah, standup"
            priority="high"
            delay={Math.round(1.4 * fps)}
          />
          <TaskItem
            text="Set up staging environment for QA"
            source="Sarah, standup"
            priority="medium"
            delay={Math.round(1.8 * fps)}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
