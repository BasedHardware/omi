import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { AbsoluteFill } from "remotion";
import { SearchScene } from "./SearchScene";
import { SearchLostCopyScene } from "./SearchLostCopyScene";
import { SearchTerminalScene } from "./SearchTerminalScene";
import { TimelineScene } from "./TimelineScene";
import { UseCasesScene } from "./UseCasesScene";

// 5 scenes: Search (140) + LostCopy (140) + Terminal (130) + Timeline (130) + UseCases (150)
// 4 transitions * 20 = 80
// Total: 690 - 80 = 610 frames ≈ 20.3 seconds at 30fps

export const RewindComposition = () => {
  const transitionDuration = 20;

  return (
    <AbsoluteFill style={{ background: "#0a0a0a" }}>
      <TransitionSeries>
        {/* Scene 1: Search — find anything (product launch date) */}
        <TransitionSeries.Sequence durationInFrames={140}>
          <SearchScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 2: Search — recover lost ad copy (closed tab) */}
        <TransitionSeries.Sequence durationInFrames={140}>
          <SearchLostCopyScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 3: Search — find forgotten terminal command */}
        <TransitionSeries.Sequence durationInFrames={130}>
          <SearchTerminalScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 4: Timeline — scrub through your day */}
        <TransitionSeries.Sequence durationInFrames={130}>
          <TimelineScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 5: Use cases — 6 idea cards */}
        <TransitionSeries.Sequence durationInFrames={150}>
          <UseCasesScene />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
