import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const logoScale = spring({ frame, fps, config: { damping: 12 } });
  const logoRotate = interpolate(spring({ frame, fps, config: { damping: 200 } }), [0, 1], [180, 0]);

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

  // Floating particles
  const particles = Array.from({ length: 15 }, (_, i) => {
    const x = (i * 137.5) % 100;
    const baseY = (i * 73.1) % 100;
    const y = baseY + Math.sin((frame + i * 20) / 30) * 3;
    const size = 2 + (i % 3);
    const opacity = interpolate(frame, [0, fps], [0, 0.12 + (i % 5) * 0.04], {
      extrapolateRight: "clamp",
    });
    return { x, y, size, opacity };
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
        background: "linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%)",
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
            background: i % 2 === 0 ? "#6366f1" : "#818cf8",
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
          gap: 10,
        }}
      >
        {/* Glow ring */}
        <div
          style={{
            position: "absolute",
            width: 120,
            height: 120,
            borderRadius: "50%",
            border: "2px solid #6366f1",
            opacity: ringOpacity,
            transform: `scale(${ringScale * 1.5})`,
            boxShadow: "0 0 40px rgba(99, 102, 241, 0.3)",
          }}
        />

        {/* Omi Logo */}
        <div
          style={{
            transform: `scale(${logoScale}) rotate(${logoRotate}deg)`,
            borderRadius: 16,
            overflow: "hidden",
            boxShadow: "0 12px 40px rgba(99, 102, 241, 0.4)",
          }}
        >
          <Img src={staticFile("omi-logo.png")} width={64} height={64} />
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
            Meet Omi
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
              color: "#a5b4fc",
              margin: 0,
              maxWidth: 400,
            }}
          >
            Your proactive AI that sees, hears, and helps
          </p>
        </div>
      </div>
    </AbsoluteFill>
  );
};
