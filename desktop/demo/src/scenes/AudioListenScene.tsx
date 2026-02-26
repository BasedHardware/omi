import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const AudioWaveform: React.FC = () => {
  const frame = useCurrentFrame();
  const bars = 40;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 1.5, height: 40 }}>
      {Array.from({ length: bars }, (_, i) => {
        const frequency = Math.sin((frame + i * 8) / 10) * 0.5 + 0.5;
        const secondary = Math.cos((frame + i * 5) / 15) * 0.3 + 0.3;
        const height = (frequency * 0.6 + secondary * 0.4) * 35 + 5;

        return (
          <div
            key={i}
            style={{
              width: 3,
              height,
              borderRadius: 2,
              background: `linear-gradient(180deg, #6366f1, #a78bfa)`,
              opacity: 0.7 + frequency * 0.3,
              transition: "none",
            }}
          />
        );
      })}
    </div>
  );
};

const TranscriptLine: React.FC<{ text: string; speaker: string; delay: number; color: string }> = ({
  text,
  speaker,
  delay,
  color,
}) => {
  const frame = useCurrentFrame();

  const charCount = Math.floor(
    interpolate(frame, [delay, delay + text.length * 0.8], [0, text.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  const opacity = interpolate(frame, [delay - 5, delay], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (charCount <= 0) return null;

  return (
    <div style={{ opacity, display: "flex", gap: 8, alignItems: "flex-start" }}>
      <div
        style={{
          width: 22,
          height: 22,
          borderRadius: "50%",
          background: color,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 9,
          fontWeight: 700,
          color: "white",
          flexShrink: 0,
        }}
      >
        {speaker[0]}
      </div>
      <div>
        <div style={{ color: "#a1a1aa", fontSize: 8, fontWeight: 600, marginBottom: 1 }}>{speaker}</div>
        <div style={{ color: "#e5e7eb", fontSize: 10, lineHeight: 1.5 }}>
          {text.slice(0, charCount)}
          {charCount < text.length && (
            <span style={{ opacity: Math.sin(frame * 0.3) > 0 ? 1 : 0, color: "#6366f1" }}>|</span>
          )}
        </div>
      </div>
    </div>
  );
};

export const AudioListenScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const contentOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const panelScale = spring({ frame, fps, config: { damping: 200 } });

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
          opacity: contentOpacity,
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
          Audio Transcription
        </span>
      </div>

      <div style={{ display: "flex", gap: 20, height: "100%", alignItems: "center", marginTop: 10 }}>
        {/* Left panel - Microphone visualization */}
        <div
          style={{
            flex: 0.8,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
            opacity: contentOpacity,
          }}
        >
          {/* Mic icon with pulse */}
          <div style={{ position: "relative" }}>
            <div
              style={{
                width: 50,
                height: 50,
                borderRadius: "50%",
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: `0 0 ${20 + Math.sin(frame * 0.2) * 10}px rgba(99, 102, 241, ${0.3 + Math.sin(frame * 0.2) * 0.2})`,
              }}
            >
              <span style={{ fontSize: 22 }}>🎙️</span>
            </div>
            {/* Pulse rings */}
            {[1, 2, 3].map((ring) => {
              const ringScale = 1 + ((frame * 0.02 + ring * 0.3) % 1) * 0.8;
              const ringOpacity = 1 - ((frame * 0.02 + ring * 0.3) % 1);
              return (
                <div
                  key={ring}
                  style={{
                    position: "absolute",
                    inset: -10,
                    borderRadius: "50%",
                    border: "1px solid #6366f1",
                    opacity: ringOpacity * 0.3,
                    transform: `scale(${ringScale})`,
                  }}
                />
              );
            })}
          </div>

          <AudioWaveform />

          <h2 style={{ color: "white", fontSize: 18, fontWeight: 700, margin: 0, textAlign: "center" }}>
            Hears everything
          </h2>
          <p style={{ color: "#a1a1aa", fontSize: 10, textAlign: "center", lineHeight: 1.6, margin: 0, maxWidth: 200 }}>
            Real-time transcription of meetings, calls, and conversations with speaker detection.
          </p>
        </div>

        {/* Right panel - Live transcript */}
        <div
          style={{
            flex: 1.2,
            height: "75%",
            background: "rgba(30, 30, 46, 0.8)",
            borderRadius: 10,
            border: "1px solid rgba(99, 102, 241, 0.15)",
            padding: 14,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            opacity: contentOpacity,
            transform: `scale(${interpolate(panelScale, [0, 1], [0.95, 1])})`,
            overflow: "hidden",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "#ef4444",
                boxShadow: `0 0 ${Math.sin(frame * 0.15) > 0 ? 6 : 3}px rgba(239, 68, 68, 0.5)`,
              }}
            />
            <span style={{ color: "#ef4444", fontSize: 9, fontWeight: 600 }}>LIVE</span>
            <span style={{ color: "#6b7280", fontSize: 9 }}>Team Standup — 10:32 AM</span>
          </div>

          <TranscriptLine
            speaker="Sarah"
            text="The new onboarding flow is almost done. We reduced the steps from ten to four."
            delay={Math.round(0.5 * fps)}
            color="#6366f1"
          />
          <TranscriptLine
            speaker="Mike"
            text="Nice! What about the permission screens? Are those still in the main flow?"
            delay={Math.round(1.8 * fps)}
            color="#22c55e"
          />
          <TranscriptLine
            speaker="Sarah"
            text="No, we moved them to contextual triggers. Users only see them when they need a feature."
            delay={Math.round(3 * fps)}
            color="#6366f1"
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
