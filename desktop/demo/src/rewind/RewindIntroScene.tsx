import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const RewindIntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const iconScale = spring({ frame, fps, config: { damping: 12 } });

  const titleOpacity = interpolate(frame, [0.4 * fps, 0.8 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(
    spring({ frame, fps, delay: Math.round(0.4 * fps), config: { damping: 200 } }),
    [0, 1],
    [20, 0]
  );

  const subtitleOpacity = interpolate(frame, [0.8 * fps, 1.2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const subtitleY = interpolate(
    spring({ frame, fps, delay: Math.round(0.8 * fps), config: { damping: 200 } }),
    [0, 1],
    [15, 0]
  );

  // Floating particles with clock/time theme
  const particles = Array.from({ length: 20 }, (_, i) => {
    const x = (i * 137.5) % 100;
    const baseY = (i * 73.1) % 100;
    const y = baseY + Math.sin((frame + i * 20) / 30) * 3;
    const size = 2 + (i % 3);
    const opacity = interpolate(frame, [0, fps], [0, 0.1 + (i % 5) * 0.03], {
      extrapolateRight: "clamp",
    });
    return { x, y, size, opacity };
  });

  // Rotating clock hands animation
  const clockRotation = interpolate(frame, [0, 2 * fps], [0, -360], {
    extrapolateRight: "clamp",
  });

  // Glowing ring
  const ringScale = spring({ frame, fps, delay: 5, config: { damping: 15 } });
  const ringOpacity = interpolate(frame, [0.2 * fps, 0.6 * fps], [0.6, 0.2], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
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
          gap: 12,
        }}
      >
        {/* Glow ring */}
        <div
          style={{
            position: "absolute",
            width: 120,
            height: 120,
            borderRadius: "50%",
            border: "2px solid #8b5cf6",
            opacity: ringOpacity,
            transform: `scale(${ringScale * 1.5})`,
            boxShadow: "0 0 40px rgba(139, 92, 246, 0.3)",
          }}
        />

        {/* Rewind icon — clock with arrow */}
        <div
          style={{
            transform: `scale(${iconScale})`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <svg
            width={64}
            height={64}
            viewBox="0 0 24 24"
            fill="none"
            style={{ filter: "drop-shadow(0 8px 24px rgba(139, 92, 246, 0.5))" }}
          >
            {/* Circular arrow */}
            <path
              d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"
              fill="#8b5cf6"
            />
            {/* Clock hands */}
            <g transform={`rotate(${clockRotation} 12 13)`}>
              <line x1="12" y1="13" x2="12" y2="9" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="12" y1="13" x2="15" y2="13" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
            </g>
          </svg>
        </div>

        {/* Title */}
        <div
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            textAlign: "center",
          }}
        >
          <h1
            style={{
              fontSize: 42,
              fontWeight: 800,
              color: "white",
              margin: 0,
              letterSpacing: -1.5,
            }}
          >
            Rewind
          </h1>
        </div>

        {/* Subtitle */}
        <div
          style={{
            opacity: subtitleOpacity,
            transform: `translateY(${subtitleY}px)`,
            textAlign: "center",
          }}
        >
          <p
            style={{
              fontSize: 16,
              fontWeight: 400,
              color: "#c4b5fd",
              margin: 0,
              maxWidth: 420,
            }}
          >
            Search anything you've ever seen on your screen
          </p>
        </div>
      </div>
    </AbsoluteFill>
  );
};
