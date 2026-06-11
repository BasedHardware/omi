import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const PrivacyItem: React.FC<{ icon: string; title: string; description: string; opacity: number; y: number }> = ({
  icon, title, description, opacity, y,
}) => (
  <div
    style={{
      opacity,
      transform: `translateY(${y}px)`,
      display: "flex",
      alignItems: "flex-start",
      gap: 12,
      padding: "10px 0",
    }}
  >
    <div
      style={{
        width: 36,
        height: 36,
        borderRadius: 10,
        background: "rgba(34, 197, 94, 0.12)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 18,
        flexShrink: 0,
      }}
    >
      {icon}
    </div>
    <div>
      <div style={{ color: "white", fontSize: 12, fontWeight: 600 }}>{title}</div>
      <div style={{ color: "#a1a1aa", fontSize: 10, lineHeight: 1.5, marginTop: 2 }}>{description}</div>
    </div>
  </div>
);

export const PrivacyScene: React.FC = () => {
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

  const items = [
    {
      icon: "💻",
      title: "100% local storage",
      description: "All screenshots are stored on your Mac. Nothing leaves your device.",
    },
    {
      icon: "🔒",
      title: "Password apps excluded",
      description: "1Password, Keychain, and other sensitive apps are automatically skipped.",
    },
    {
      icon: "🗑️",
      title: "Auto-cleanup",
      description: "Old data is automatically deleted based on your retention settings.",
    },
    {
      icon: "⏸️",
      title: "Pause anytime",
      description: "One click to pause recording. You're always in control.",
    },
  ];

  // Shield icon animation
  const shieldScale = spring({ frame, fps, delay: 5, config: { damping: 12 } });
  const shieldGlow = interpolate(frame, [0.3 * fps, 1 * fps, 2 * fps], [0, 0.4, 0.2], {
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
          opacity: titleOpacity,
        }}
      >
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", boxShadow: "0 0 8px rgba(34, 197, 94, 0.5)" }} />
        <span style={{ color: "#22c55e", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>
          Privacy First
        </span>
      </div>

      <div style={{ display: "flex", gap: 28, height: "100%", alignItems: "center", marginTop: 10 }}>
        {/* Left — shield + headline */}
        <div
          style={{
            flex: 0.8,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 14,
          }}
        >
          <div
            style={{
              transform: `scale(${shieldScale})`,
              filter: `drop-shadow(0 0 ${shieldGlow * 40}px rgba(34, 197, 94, 0.5))`,
            }}
          >
            <svg width={80} height={80} viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L4 5v6.09c0 5.05 3.41 9.76 8 10.91 4.59-1.15 8-5.86 8-10.91V5l-8-3z"
                fill="rgba(34, 197, 94, 0.15)"
                stroke="#22c55e"
                strokeWidth="1.5"
              />
              <path
                d="M9 12l2 2 4-4"
                stroke="#22c55e"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>

          <div style={{ opacity: titleOpacity, transform: `translateY(${titleY}px)`, textAlign: "center" }}>
            <h2 style={{ color: "white", fontSize: 22, fontWeight: 700, margin: 0 }}>
              Your data stays yours
            </h2>
            <p style={{ color: "#a1a1aa", fontSize: 11, lineHeight: 1.5, margin: "6px 0 0", maxWidth: 260 }}>
              Rewind is built with privacy at its core. Everything stays on your machine.
            </p>
          </div>
        </div>

        {/* Right — privacy items */}
        <div
          style={{
            flex: 1.2,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {items.map((item, i) => {
            const delay = 0.5 * fps + i * 10;
            const itemOpacity = interpolate(frame, [delay, delay + 8], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const itemY = interpolate(
              spring({ frame, fps, delay: Math.round(delay), config: { damping: 200 } }),
              [0, 1],
              [10, 0]
            );
            return <PrivacyItem key={i} {...item} opacity={itemOpacity} y={itemY} />;
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
