import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const RewindOutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const iconScale = spring({ frame, fps, config: { damping: 12 } });

  const titleOpacity = interpolate(frame, [0.3 * fps, 0.6 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(
    spring({ frame, fps, delay: Math.round(0.3 * fps), config: { damping: 200 } }),
    [0, 1],
    [20, 0]
  );

  const subtitleOpacity = interpolate(frame, [0.6 * fps, 1 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Pulse animation for CTA
  const pulse = interpolate(
    frame % (fps * 1.5),
    [0, fps * 0.75, fps * 1.5],
    [1, 1.05, 1],
    { extrapolateRight: "clamp" }
  );

  const ctaOpacity = interpolate(frame, [1 * fps, 1.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Floating particles
  const particles = Array.from({ length: 12 }, (_, i) => {
    const x = (i * 137.5) % 100;
    const baseY = (i * 73.1) % 100;
    const y = baseY + Math.sin((frame + i * 20) / 25) * 4;
    const size = 2 + (i % 3);
    const opacity = interpolate(frame, [0, fps * 0.5], [0, 0.08 + (i % 4) * 0.03], {
      extrapolateRight: "clamp",
    });
    return { x, y, size, opacity };
  });

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #0a0a0a 0%, #0f172a 50%, #0a0a0a 100%)",
        fontFamily: "Inter, sans-serif",
      }}
    >
      {particles.map((p, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
            borderRadius: "50%",
            background: i % 2 === 0 ? "#8b5cf6" : "#a78bfa",
            opacity: p.opacity,
          }}
        />
      ))}

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          gap: 14,
        }}
      >
        {/* Rewind icon */}
        <div style={{ transform: `scale(${iconScale})` }}>
          <svg
            width={48}
            height={48}
            viewBox="0 0 24 24"
            fill="none"
            style={{ filter: "drop-shadow(0 6px 20px rgba(139, 92, 246, 0.4))" }}
          >
            <path
              d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"
              fill="#8b5cf6"
            />
          </svg>
        </div>

        {/* Title */}
        <div style={{ opacity: titleOpacity, transform: `translateY(${titleY}px)`, textAlign: "center" }}>
          <h1
            style={{
              fontSize: 36,
              fontWeight: 800,
              color: "white",
              margin: 0,
              letterSpacing: -1,
            }}
          >
            Start exploring
          </h1>
        </div>

        {/* Subtitle */}
        <div style={{ opacity: subtitleOpacity, textAlign: "center" }}>
          <p
            style={{
              fontSize: 14,
              fontWeight: 400,
              color: "#c4b5fd",
              margin: 0,
              maxWidth: 360,
            }}
          >
            Use the search bar or scroll through your timeline to find anything
          </p>
        </div>

        {/* CTA hint */}
        <div
          style={{
            opacity: ctaOpacity,
            transform: `scale(${pulse})`,
            background: "rgba(139, 92, 246, 0.15)",
            border: "1px solid rgba(139, 92, 246, 0.3)",
            borderRadius: 10,
            padding: "10px 24px",
            marginTop: 8,
          }}
        >
          <span style={{ color: "#c4b5fd", fontSize: 12, fontWeight: 600 }}>
            ⌘ ⌥ R to open Rewind anytime
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
