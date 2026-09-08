import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FakeScreenshot: React.FC<{ app: string; title: string; color: string; active: boolean }> = ({
  app, title, color, active,
}) => (
  <div
    style={{
      width: "100%",
      height: "100%",
      background: active ? "#1a1a2e" : "#111",
      borderRadius: 8,
      border: active ? `2px solid ${color}` : "1px solid rgba(255,255,255,0.08)",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
      boxShadow: active ? `0 0 20px ${color}33` : "none",
      transition: "all 0.3s",
    }}
  >
    {/* Window chrome */}
    <div style={{ background: "#1e1e1e", padding: "4px 8px", display: "flex", alignItems: "center", gap: 4 }}>
      <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#ff5f57" }} />
      <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#febc2e" }} />
      <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#28c840" }} />
      <span style={{ color: "#888", fontSize: 7, marginLeft: 6 }}>{app}</span>
    </div>
    {/* Content placeholder */}
    <div style={{ flex: 1, padding: 8, display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ color: "#e5e5e5", fontSize: 9, fontWeight: 600 }}>{title}</div>
      <div style={{ background: "rgba(255,255,255,0.06)", height: 4, borderRadius: 2, width: "80%" }} />
      <div style={{ background: "rgba(255,255,255,0.04)", height: 4, borderRadius: 2, width: "60%" }} />
      <div style={{ background: "rgba(255,255,255,0.04)", height: 4, borderRadius: 2, width: "70%" }} />
    </div>
  </div>
);

export const TimelineScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const screenshots = [
    { app: "Google Docs", title: "Q1 Planning", color: "#4285F4" },
    { app: "VS Code", title: "dashboard.tsx", color: "#007ACC" },
    { app: "Slack", title: "#product-team", color: "#E01E5A" },
    { app: "Figma", title: "Dashboard v2", color: "#F24E1E" },
    { app: "Gmail", title: "Launch update", color: "#EA4335" },
  ];

  // Timeline scrubber animation — moves from right to left
  const scrubberProgress = interpolate(frame, [0.5 * fps, 3 * fps], [4, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const activeIndex = Math.round(scrubberProgress);

  const labelOpacity = interpolate(frame, [0, 0.2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const contentOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const contentScale = spring({ frame, fps, config: { damping: 200 } });

  const rightOpacity = interpolate(frame, [1.5 * fps, 2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Time labels for the timeline
  const times = ["9:00 AM", "10:30 AM", "11:45 AM", "1:15 PM", "2:30 PM"];

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #0a0a0a 0%, #0f172a 50%, #0a0a0a 100%)",
        fontFamily: "Inter, sans-serif",
        padding: 30,
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
          opacity: labelOpacity,
        }}
      >
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#8b5cf6", boxShadow: "0 0 8px rgba(139, 92, 246, 0.5)" }} />
        <span style={{ color: "#8b5cf6", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>
          Timeline
        </span>
      </div>

      <div style={{ display: "flex", gap: 28, height: "100%", alignItems: "center", marginTop: 10 }}>
        {/* Left — screenshot strip */}
        <div
          style={{
            flex: 1.2,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            opacity: contentOpacity,
            transform: `scale(${interpolate(contentScale, [0, 1], [0.97, 1])})`,
          }}
        >
          {/* Main screenshot (active one) */}
          <div style={{ height: 180, borderRadius: 10, overflow: "hidden" }}>
            <FakeScreenshot {...screenshots[activeIndex]} active={true} />
          </div>

          {/* Timeline strip */}
          <div style={{ display: "flex", gap: 6, position: "relative" }}>
            {screenshots.map((s, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 3,
                }}
              >
                <div style={{ height: 48, width: "100%", borderRadius: 4, overflow: "hidden" }}>
                  <FakeScreenshot {...s} active={i === activeIndex} />
                </div>
                <span style={{ color: i === activeIndex ? "#8b5cf6" : "#6b7280", fontSize: 7, fontWeight: i === activeIndex ? 600 : 400 }}>
                  {times[i]}
                </span>
              </div>
            ))}

            {/* Scrubber indicator */}
            <div
              style={{
                position: "absolute",
                bottom: -4,
                left: `${(scrubberProgress / 4) * 100}%`,
                width: "20%",
                height: 2,
                background: "#8b5cf6",
                borderRadius: 1,
                boxShadow: "0 0 8px rgba(139, 92, 246, 0.6)",
                transition: "left 0.1s linear",
              }}
            />
          </div>
        </div>

        {/* Right — explanation */}
        <div
          style={{
            flex: 0.8,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            opacity: rightOpacity,
          }}
        >
          <h2 style={{ color: "white", fontSize: 20, fontWeight: 700, margin: 0 }}>
            Scroll through your day
          </h2>
          <p style={{ color: "#a1a1aa", fontSize: 11, lineHeight: 1.6, margin: 0 }}>
            Browse your screen timeline like a visual history. Scrub backward to revisit anything you were working on — every app, every tab, every moment.
          </p>

          <div
            style={{
              background: "rgba(139, 92, 246, 0.1)",
              border: "1px solid rgba(139, 92, 246, 0.2)",
              borderRadius: 8,
              padding: 10,
              marginTop: 4,
            }}
          >
            <div style={{ color: "#a78bfa", fontSize: 8, fontWeight: 600, marginBottom: 6, textTransform: "uppercase", letterSpacing: 1 }}>
              How to navigate
            </div>
            {[
              { icon: "🖱️", text: "Scroll to move through time" },
              { icon: "⌨️", text: "Arrow keys for precision" },
              { icon: "🔍", text: "Search to jump to a moment" },
            ].map((item, i) => {
              const tipOpacity = interpolate(
                frame,
                [2.5 * fps + i * 6, 2.8 * fps + i * 6],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              );
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, opacity: tipOpacity, padding: "3px 0" }}>
                  <span style={{ fontSize: 11 }}>{item.icon}</span>
                  <span style={{ color: "#d1d5db", fontSize: 10 }}>{item.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
