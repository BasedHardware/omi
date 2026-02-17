import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const logoScale = spring({ frame, fps, config: { damping: 12 } });

  const titleOpacity = interpolate(frame, [0.3 * fps, 0.6 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(
    spring({ frame, fps, delay: Math.round(0.3 * fps), config: { damping: 200 } }),
    [0, 1],
    [15, 0]
  );

  const ctaOpacity = interpolate(frame, [0.8 * fps, 1.1 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const ctaScale = spring({ frame, fps, delay: Math.round(0.8 * fps), config: { damping: 15 } });

  const features = ["Screen Monitoring", "Audio Transcription", "Proactive Advice", "Task Extraction", "Focus Tracking"];

  const particles = Array.from({ length: 20 }, (_, i) => {
    const x = (i * 137.5) % 100;
    const baseY = (i * 73.1) % 100;
    const y = baseY + Math.sin((frame + i * 15) / 25) * 3;
    const size = 1.5 + (i % 4);
    const opacity = 0.04 + (i % 5) * 0.02;
    return { x, y, size, opacity };
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
            background: i % 3 === 0 ? "#6366f1" : i % 3 === 1 ? "#8b5cf6" : "#a78bfa",
            opacity: p.opacity,
          }}
        />
      ))}

      <div
        style={{
          position: "absolute",
          top: "40%",
          left: "50%",
          width: 300,
          height: 300,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(99, 102, 241, 0.1), transparent)",
          transform: "translate(-50%, -50%)",
        }}
      />

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
        {/* Omi Logo */}
        <div
          style={{
            transform: `scale(${logoScale})`,
            borderRadius: 14,
            overflow: "hidden",
            boxShadow: "0 12px 40px rgba(99, 102, 241, 0.4)",
          }}
        >
          <Img src={staticFile("omi-logo.png")} width={52} height={52} />
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
              fontSize: 36,
              fontWeight: 800,
              color: "white",
              margin: 0,
              letterSpacing: -1.5,
            }}
          >
            Your AI, always on
          </h1>
        </div>

        {/* Feature pills */}
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            justifyContent: "center",
            maxWidth: 500,
            opacity: ctaOpacity,
          }}
        >
          {features.map((feature, i) => {
            const pillScale = spring({
              frame,
              fps,
              delay: Math.round(1 * fps + i * 3),
              config: { damping: 15 },
            });
            return (
              <div
                key={i}
                style={{
                  transform: `scale(${pillScale})`,
                  background: "rgba(99, 102, 241, 0.1)",
                  border: "1px solid rgba(99, 102, 241, 0.25)",
                  borderRadius: 14,
                  padding: "4px 12px",
                  color: "#a5b4fc",
                  fontSize: 9,
                  fontWeight: 500,
                }}
              >
                {feature}
              </div>
            );
          })}
        </div>

        {/* CTA */}
        <div
          style={{
            opacity: ctaOpacity,
            transform: `scale(${ctaScale})`,
            marginTop: 8,
          }}
        >
          <div
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              borderRadius: 10,
              padding: "8px 24px",
              color: "white",
              fontSize: 14,
              fontWeight: 700,
              boxShadow: "0 6px 24px rgba(99, 102, 241, 0.4)",
            }}
          >
            Let's get started
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
