import "./index.css";
import { Composition } from "remotion";
import { MyComposition } from "./Composition";
import { RewindComposition } from "./rewind/RewindComposition";

// OmiDemo duration: 220+220+220 = 660 frames
// Minus 2 transitions * 18 = 36
// Total: 624 frames = 20.8 seconds at 30fps

// RewindDemo duration: 140+140+130+130+150 = 690 frames
// Minus 4 transitions * 20 = 80
// Total: 610 frames ≈ 20.3 seconds at 30fps

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="OmiDemo"
        component={MyComposition}
        durationInFrames={624}
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
