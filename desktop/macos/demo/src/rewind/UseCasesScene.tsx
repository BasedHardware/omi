import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const UseCaseCard: React.FC<{
  icon: string;
  title: string;
  description: string;
  example: string;
  opacity: number;
  scale: number;
}> = ({ icon, title, description, example, opacity, scale }) => (
  <div
    style={{
      opacity,
      transform: `scale(${scale})`,
      background: "rgba(255, 255, 255, 0.04)",
      border: "1px solid rgba(139, 92, 246, 0.15)",
      borderRadius: 10,
      padding: 12,
      flex: 1,
      display: "flex",
      flexDirection: "column",
      gap: 5,
      minWidth: 0,
    }}
  >
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          width: 30,
          height: 30,
          borderRadius: 8,
          background: "rgba(139, 92, 246, 0.12)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 16,
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div style={{ color: "white", fontSize: 11, fontWeight: 700 }}>{title}</div>
    </div>
    <div style={{ color: "#a1a1aa", fontSize: 9, lineHeight: 1.4 }}>{description}</div>
    <div
      style={{
        background: "rgba(139, 92, 246, 0.08)",
        borderRadius: 5,
        padding: "4px 8px",
        marginTop: "auto",
      }}
    >
      <span style={{ color: "#c4b5fd", fontSize: 8, fontStyle: "italic" }}>
        "{example}"
      </span>
    </div>
  </div>
);

export const UseCasesScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(
    spring({ frame, fps, config: { damping: 200 } }),
    [0, 1],
    [15, 0]
  );

  const useCases = [
    {
      icon: "💻",
      title: "Code & terminal",
      description: "Find that snippet, function, or terminal command from earlier.",
      example: "ssh deploy command",
    },
    {
      icon: "📋",
      title: "Meeting recall",
      description: "Recall slides, shared screens, or chat from any call.",
      example: "quarterly review deck",
    },
    {
      icon: "🌐",
      title: "Webpages & articles",
      description: "Revisit any site or article without remembering the URL.",
      example: "pricing comparison table",
    },
    {
      icon: "💬",
      title: "Chat & messages",
      description: "Find that Slack message, email, or conversation you saw fly by.",
      example: "API key from Slack",
    },
    {
      icon: "🎓",
      title: "Learning & courses",
      description: "Search through lectures, tutorials, or YouTube videos you watched.",
      example: "SwiftUI animation tutorial",
    },
    {
      icon: "📝",
      title: "Lost work recovery",
      description: "Browser crashed? Forgot to save? Scroll back and recover your data.",
      example: "unsaved doc draft",
    },
  ];

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
          opacity: titleOpacity,
        }}
      >
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#8b5cf6", boxShadow: "0 0 8px rgba(139, 92, 246, 0.5)" }} />
        <span style={{ color: "#8b5cf6", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>
          Ideas
        </span>
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          justifyContent: "center",
          gap: 14,
          marginTop: 10,
        }}
      >
        {/* Heading */}
        <div
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            textAlign: "center",
          }}
        >
          <h2 style={{ color: "white", fontSize: 20, fontWeight: 700, margin: 0 }}>
            What can you find?
          </h2>
          <p style={{ color: "#a1a1aa", fontSize: 11, margin: "4px 0 0", lineHeight: 1.4 }}>
            Anything that was ever on your screen
          </p>
        </div>

        {/* Row 1 */}
        <div style={{ display: "flex", gap: 10, padding: "0 6px" }}>
          {useCases.slice(0, 3).map((uc, i) => {
            const delay = 0.4 * fps + i * 10;
            const cardOpacity = interpolate(frame, [delay, delay + 8], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const cardScale = interpolate(
              spring({ frame, fps, delay: Math.round(delay), config: { damping: 15 } }),
              [0, 1],
              [0.9, 1]
            );
            return <UseCaseCard key={i} {...uc} opacity={cardOpacity} scale={cardScale} />;
          })}
        </div>

        {/* Row 2 */}
        <div style={{ display: "flex", gap: 10, padding: "0 6px" }}>
          {useCases.slice(3, 6).map((uc, i) => {
            const delay = 1.2 * fps + i * 10;
            const cardOpacity = interpolate(frame, [delay, delay + 8], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const cardScale = interpolate(
              spring({ frame, fps, delay: Math.round(delay), config: { damping: 15 } }),
              [0, 1],
              [0.9, 1]
            );
            return <UseCaseCard key={i + 3} {...uc} opacity={cardOpacity} scale={cardScale} />;
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
