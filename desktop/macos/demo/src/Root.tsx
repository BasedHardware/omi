import "./index.css";
import { Composition } from "remotion";
import { MyComposition } from "./Composition";
import { RewindComposition } from "./rewind/RewindComposition";

// OmiDemo duration: 90+120+140+120+120+120+120+90 = 920 frames
// Minus 7 transitions * 20 = 140
// Total: 780 frames = 26 seconds at 30fps

// RewindDemo duration: 140+140+130+130+150 = 690 frames
// Minus 4 transitions * 20 = 80
// Total: 610 frames ≈ 20.3 seconds at 30fps

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="OmiDemo"
        component={MyComposition}
        durationInFrames={780}
        fps={30}
        width={960}
        height={540}
      />
      <Composition
        id="RewindDemo"
        component={RewindComposition}
        durationInFrames={610}
        fps={30}
        width={960}
        height={540}
      />
    </>
  );
};
