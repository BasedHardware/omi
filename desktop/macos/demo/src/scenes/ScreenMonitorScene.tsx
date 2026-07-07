import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Sequence,
} from "remotion";
import { GoogleDocsIcon } from "../icons/AppIcons";

const FakeGoogleDoc: React.FC = () => {
  const frame = useCurrentFrame();

  const docLines = [
    { text: "Q1 Product Launch Plan", style: "title" as const },
    { text: "" },
    { text: "Overview", style: "heading" as const },
    { text: "We're launching the new dashboard redesign on March 15th." },
    { text: "The goal is to improve user activation by 40% through a" },
    { text: "simplified onboarding flow and better empty states." },
    { text: "" },
    { text: "Key Milestones", style: "heading" as const },
    { text: "• Design review — complete by Feb 20" },
    { text: "• Engineering sprint — Feb 21 to Mar 10" },
    { text: "• QA and staging — Mar 11 to Mar 14" },
    { text: "• Launch day — Mar 15 🚀" },
  ];

  return (
    <div
      style={{
        background: "#ffffff",
        borderRadius: 8,
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Chrome-like toolbar */}
      <div style={{ background: "#f1f3f4", padding: "6px 10px", display: "flex", alignItems: "center", gap: 6, borderBottom: "1px solid #e0e0e0" }}>
        <div style={{ display: "flex", gap: 4 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#ff5f57" }} />
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#febc2e" }} />
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#28c840" }} />
        </div>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6, marginLeft: 8 }}>
          <GoogleDocsIcon size={14} />
          <span style={{ color: "#333", fontSize: 10, fontWeight: 500 }}>Q1 Product Launch Plan — Google Docs</span>
        </div>
      </div>

      {/* Doc toolbar */}
      <div style={{ background: "#f8f9fa", padding: "4px 12px", borderBottom: "1px solid #e8eaed", display: "flex", gap: 12 }}>
        {["File", "Edit", "View", "Insert", "Format"].map((item) => (
          <span key={item} style={{ color: "#5f6368", fontSize: 9 }}>{item}</span>
        ))}
      </div>

      {/* Document content */}
      <div style={{ flex: 1, padding: "16px 28px", background: "white" }}>
        {docLines.map((line, i) => {
          const charCount = Math.floor(
            interpolate(frame, [i * 3, i * 3 + 12], [0, (line.text || "").length], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          );

          if (!line.text) return <div key={i} style={{ height: 8 }} />;

          const isTitle = line.style === "title";
          const isHeading = line.style === "heading";

          return (
            <div
              key={i}
              style={{
                color: "#202124",
                fontSize: isTitle ? 16 : isHeading ? 12 : 10,
                fontWeight: isTitle ? 700 : isHeading ? 600 : 400,
                lineHeight: 1.6,
                marginBottom: isTitle ? 4 : isHeading ? 2 : 0,
              }}
            >
              {line.text.slice(0, charCount)}
              {charCount < line.text.length && charCount > 0 && (
                <span style={{ opacity: Math.sin(frame * 0.3) > 0 ? 1 : 0, color: "#1a73e8" }}>|</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ScanLine: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const scanY = interpolate(frame, [0, 2 * fps], [0, 100], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: `${scanY}%`,
        height: 2,
        background: "linear-gradient(90deg, transparent, #6366f1, transparent)",
        boxShadow: "0 0 15px rgba(99, 102, 241, 0.6)",
        opacity: 0.8,
      }}
    />
  );
};

export const ScreenMonitorScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const screenScale = spring({ frame, fps, config: { damping: 200 } });
  const screenOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const badgeOpacity = interpolate(frame, [1 * fps, 1.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const badgeScale = spring({ frame, fps, delay: Math.round(1 * fps), config: { damping: 12 } });

  const insightOpacity = interpolate(frame, [2 * fps, 2.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const insightX = interpolate(
    spring({ frame, fps, delay: Math.round(2 * fps), config: { damping: 200 } }),
    [0, 1],
    [20, 0]
  );

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%)",
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
          opacity: screenOpacity,
        }}
      >
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", boxShadow: "0 0 8px rgba(34, 197, 94, 0.5)" }} />
        <span style={{ color: "#6366f1", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>Screen Monitoring</span>
      </div>

      <div style={{ display: "flex", gap: 24, height: "100%", alignItems: "center", marginTop: 10 }}>
        {/* Google Doc */}
        <div
          style={{
            flex: 1.2,
            height: "80%",
            opacity: screenOpacity,
            transform: `scale(${interpolate(screenScale, [0, 1], [0.95, 1])})`,
            position: "relative",
            borderRadius: 10,
            overflow: "hidden",
            border: "1px solid rgba(99, 102, 241, 0.2)",
            boxShadow: "0 0 30px rgba(99, 102, 241, 0.1)",
          }}
        >
          <FakeGoogleDoc />
          <Sequence from={Math.round(0.5 * fps)} durationInFrames={Math.round(2.5 * fps)} premountFor={Math.round(0.5 * fps)}>
            <ScanLine />
          </Sequence>

          {/* Badge */}
          <div
            style={{
              position: "absolute",
              top: 8,
              right: 8,
              opacity: badgeOpacity,
              transform: `scale(${badgeScale})`,
              background: "rgba(99, 102, 241, 0.9)",
              borderRadius: 14,
              padding: "3px 10px",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <div style={{ width: 5, height: 5, borderRadius: "50%", background: "#22c55e", boxShadow: "0 0 4px rgba(34, 197, 94, 0.8)" }} />
            <span style={{ color: "white", fontSize: 8, fontWeight: 600 }}>Omi is watching</span>
          </div>
        </div>

        {/* Right panel */}
        <div
          style={{
            flex: 0.8,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            opacity: insightOpacity,
            transform: `translateX(${insightX}px)`,
          }}
        >
          <h2 style={{ color: "white", fontSize: 20, fontWeight: 700, margin: 0 }}>Sees your screen</h2>
          <p style={{ color: "#a1a1aa", fontSize: 11, lineHeight: 1.6, margin: 0 }}>
            Omi monitors your screen to understand what you're working on — docs, code, emails, meetings.
          </p>

          <div
            style={{
              background: "rgba(99, 102, 241, 0.1)",
              border: "1px solid rgba(99, 102, 241, 0.2)",
              borderRadius: 8,
              padding: 10,
              marginTop: 4,
            }}
          >
            <div style={{ color: "#818cf8", fontSize: 8, fontWeight: 600, marginBottom: 6, textTransform: "uppercase", letterSpacing: 1 }}>
              Detected Context
            </div>
            {[
              { icon: "📄", text: "Editing launch plan doc" },
              { icon: "📅", text: "Launch date: March 15" },
              { icon: "✅", text: "4 action items detected" },
            ].map((item, i) => {
              const itemOpacity = interpolate(
                frame,
                [2.5 * fps + i * 6, 2.8 * fps + i * 6],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              );
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, opacity: itemOpacity, padding: "3px 0" }}>
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
