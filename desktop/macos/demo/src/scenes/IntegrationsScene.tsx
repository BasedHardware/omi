import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  SlackIcon,
  VSCodeIcon,
  NotionIcon,
  CalendarIcon,
  ZoomIcon,
  LinearIcon,
  GitHubIcon,
  GmailIcon,
} from "../icons/AppIcons";

const AppIcon: React.FC<{
  name: string;
  icon: React.ReactNode;
  delay: number;
  x: number;
  y: number;
}> = ({ name, icon, delay, x, y }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({ frame, fps, delay, config: { damping: 12 } });
  const scale = interpolate(entrance, [0, 1], [0, 1]);
  const opacity = interpolate(entrance, [0, 1], [0, 1]);
  const floatY = Math.sin((frame + delay) / 25) * 2;

  return (
    <div
      style={{
        position: "absolute",
        left: `${x}%`,
        top: `${y}%`,
        transform: `translate(-50%, -50%) scale(${scale}) translateY(${floatY}px)`,
        opacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 4,
      }}
    >
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: 11,
          background: "rgba(30, 30, 46, 0.9)",
          border: "1px solid rgba(99, 102, 241, 0.2)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
        }}
      >
        {icon}
      </div>
      <span style={{ color: "#9ca3af", fontSize: 8, fontWeight: 500 }}>{name}</span>
    </div>
  );
};

const DataFlowLine: React.FC<{
  x1: number; y1: number; x2: number; y2: number; delay: number;
}> = ({ x1, y1, x2, y2, delay }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = interpolate(frame, [delay, delay + fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame, [delay, delay + 10], [0, 0.25], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const dotPos = (frame * 0.02 + delay * 0.1) % 1;
  const dotX = x1 + (x2 - x1) * dotPos;
  const dotY = y1 + (y2 - y1) * dotPos;

  return (
    <>
      <line
        x1={`${x1}%`} y1={`${y1}%`}
        x2={`${x1 + (x2 - x1) * progress}%`}
        y2={`${y1 + (y2 - y1) * progress}%`}
        stroke="#6366f1" strokeWidth="1" opacity={opacity} strokeDasharray="3 3"
      />
      {progress > 0.3 && (
        <circle cx={`${dotX}%`} cy={`${dotY}%`} r="2" fill="#6366f1" opacity={0.8} />
      )}
    </>
  );
};

export const IntegrationsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOpacity = interpolate(frame, [0, 0.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const centerScale = spring({ frame, fps, config: { damping: 15 } });

  const apps = [
    { name: "Slack", icon: <SlackIcon size={24} />, x: 20, y: 25, delay: Math.round(0.5 * fps) },
    { name: "VS Code", icon: <VSCodeIcon size={24} />, x: 80, y: 20, delay: Math.round(0.7 * fps) },
    { name: "Notion", icon: <NotionIcon size={24} />, x: 15, y: 55, delay: Math.round(0.9 * fps) },
    { name: "Calendar", icon: <CalendarIcon size={24} />, x: 85, y: 50, delay: Math.round(1.1 * fps) },
    { name: "Zoom", icon: <ZoomIcon size={24} />, x: 22, y: 82, delay: Math.round(1.3 * fps) },
    { name: "Linear", icon: <LinearIcon size={24} />, x: 78, y: 80, delay: Math.round(1.5 * fps) },
    { name: "GitHub", icon: <GitHubIcon size={24} />, x: 50, y: 15, delay: Math.round(0.6 * fps) },
    { name: "Gmail", icon: <GmailIcon size={24} />, x: 50, y: 88, delay: Math.round(1.4 * fps) },
  ];

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%)",
        fontFamily: "Inter, sans-serif",
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
          opacity: headerOpacity,
          zIndex: 10,
        }}
      >
        <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#818cf8", boxShadow: "0 0 8px rgba(129, 140, 248, 0.5)" }} />
        <span style={{ color: "#6366f1", fontSize: 10, fontWeight: 600, letterSpacing: 1.5, textTransform: "uppercase" }}>Integrations</span>
      </div>

      {/* Connection lines */}
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
        {apps.map((app, i) => (
          <DataFlowLine key={i} x1={50} y1={50} x2={app.x} y2={app.y} delay={app.delay} />
        ))}
      </svg>

      {/* Center Omi hub */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: `translate(-50%, -50%) scale(${centerScale})`,
          zIndex: 5,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 4,
        }}
      >
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: 14,
            overflow: "hidden",
            boxShadow: "0 0 40px rgba(99, 102, 241, 0.4)",
          }}
        >
          <Img src={staticFile("omi-logo.png")} width={56} height={56} />
        </div>
        <span style={{ color: "white", fontSize: 10, fontWeight: 600 }}>Omi</span>
      </div>

      {/* App icons */}
      {apps.map((app, i) => (
        <AppIcon key={i} {...app} />
      ))}

      {/* Bottom text */}
      <div
        style={{
          position: "absolute",
          bottom: 20,
          left: 0,
          right: 0,
          textAlign: "center",
          opacity: interpolate(frame, [2 * fps, 2.5 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        <p style={{ color: "#a1a1aa", fontSize: 11, margin: 0 }}>
          Connects to your entire workflow — passing context seamlessly between apps
        </p>
      </div>
    </AbsoluteFill>
  );
};
