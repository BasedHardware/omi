import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const FakeSearchBar: React.FC<{ query: string; charCount: number }> = ({ query, charCount }) => {
  const frame = useCurrentFrame();
  const displayText = query.slice(0, charCount);
  const cursorVisible = Math.sin(frame * 0.3) > 0 && charCount < query.length;

  return (
    <div
      style={{
        background: "rgba(255, 255, 255, 0.08)",
        border: "1px solid rgba(139, 92, 246, 0.4)",
        borderRadius: 12,
        padding: "12px 16px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        boxShadow: "0 0 20px rgba(139, 92, 246, 0.15)",
      }}
    >
      <svg width={18} height={18} viewBox="0 0 24 24" fill="none">
        <circle cx="11" cy="11" r="7" stroke="#8b5cf6" strokeWidth="2" />
        <path d="M16 16l4.5 4.5" stroke="#8b5cf6" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span style={{ color: "white", fontSize: 14, fontWeight: 500 }}>
        {displayText}
        {cursorVisible && <span style={{ color: "#8b5cf6" }}>|</span>}
      </span>
    </div>
  );
};

const SearchResult: React.FC<{ icon: string; title: string; context: string; time: string; opacity: number; y: number; highlight?: boolean }> = ({
  icon, title, context, time, opacity, y, highlight,
}) => (
  <div
    style={{
      opacity,
      transform: `translateY(${y}px)`,
      background: highlight ? "rgba(139, 92, 246, 0.08)" : "rgba(255, 255, 255, 0.05)",
      border: highlight ? "1px solid rgba(139, 92, 246, 0.25)" : "1px solid rgba(255, 255, 255, 0.08)",
      borderRadius: 10,
      padding: "10px 14px",
      display: "flex",
      alignItems: "center",
      gap: 12,
    }}
  >
    <div
      style={{
        width: 36,
        height: 36,
        borderRadius: 8,
        background: "rgba(139, 92, 246, 0.15)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 18,
        flexShrink: 0,
      }}
    >
      {icon}
    </div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ color: "white", fontSize: 12, fontWeight: 600 }}>{title}</div>
      <div style={{ color: "#a1a1aa", fontSize: 10, marginTop: 2 }}>{context}</div>
    </div>
    <div style={{ color: "#6b7280", fontSize: 9, flexShrink: 0 }}>{time}</div>
  </div>
);

export const SearchLostCopyScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const searchQuery = "free shipping on all orders";
  const charCount = Math.floor(
    interpolate(frame, [0.3 * fps, 1.5 * fps], [0, searchQuery.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  const barOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const barScale = spring({ frame, fps, config: { damping: 200 } });

  const results = [
    { icon: "🌐", title: "Chrome — Spring Campaign Draft", context: "\"Free shipping on all orders over $50 — limited time only\"", time: "3:12 PM", highlight: true },
    { icon: "📄", title: "Google Docs — Ad Copy v3", context: "Headline B: Free shipping + 20% off spring collection", time: "1:45 PM", highlight: false },
    { icon: "💬", title: "Slack — #marketing", context: "\"Can we add free shipping to the banner copy?\"", time: "11:30 AM", highlight: false },
  ];

  const labelOpacity = interpolate(frame, [0, 0.2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const headingOpacity = interpolate(frame, [2.8 * fps, 3.2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

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
          Recover Lost Work
        </span>
      </div>

      <div style={{ display: "flex", gap: 28, height: "100%", alignItems: "center", marginTop: 10 }}>
        {/* Left — search demo */}
        <div
          style={{
            flex: 1.2,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            opacity: barOpacity,
            transform: `scale(${interpolate(barScale, [0, 1], [0.97, 1])})`,
          }}
        >
          <FakeSearchBar query={searchQuery} charCount={charCount} />

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 4 }}>
            {results.map((r, i) => {
              const delay = 1.8 * fps + i * 8;
              const rOpacity = interpolate(frame, [delay, delay + 8], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              const rY = interpolate(
                spring({ frame, fps, delay: Math.round(delay), config: { damping: 200 } }),
                [0, 1],
                [12, 0]
              );
              return <SearchResult key={i} {...r} opacity={rOpacity} y={rY} />;
            })}
          </div>
        </div>

        {/* Right — story */}
        <div
          style={{
            flex: 0.8,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            opacity: headingOpacity,
          }}
        >
          <h2 style={{ color: "white", fontSize: 20, fontWeight: 700, margin: 0 }}>
            Closed a tab by accident?
          </h2>
          <p style={{ color: "#a1a1aa", fontSize: 11, lineHeight: 1.6, margin: 0 }}>
            You were editing ad copy in the browser and accidentally closed the tab. Instead of rewriting from scratch, search for any phrase you remember — Rewind finds the exact screen where you had it open.
          </p>

          <div
            style={{
              background: "rgba(34, 197, 94, 0.08)",
              border: "1px solid rgba(34, 197, 94, 0.2)",
              borderRadius: 8,
              padding: 10,
              marginTop: 4,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span style={{ fontSize: 16 }}>✅</span>
            <span style={{ color: "#86efac", fontSize: 10, lineHeight: 1.4 }}>
              Copy recovered from the screenshot — no need to rewrite anything
            </span>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
