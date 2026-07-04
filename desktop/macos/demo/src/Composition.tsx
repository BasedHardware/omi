import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { AbsoluteFill } from "remotion";
import {
  AgentRouterFallbackScene,
  AgentRouterRouteScene,
  AgentRouterSetupScene,
} from "./scenes/AgentRouterScene";

export const MyComposition = () => {
  const transitionDuration = 18;

  return (
    <AbsoluteFill style={{ background: "#0a0a0a" }}>
      <TransitionSeries>
        {/* Scene 1: Route - pick the best agent */}
        <TransitionSeries.Sequence durationInFrames={220}>
          <AgentRouterRouteScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 2: Setup - guide the user when the agent is missing */}
        <TransitionSeries.Sequence durationInFrames={220}>
          <AgentRouterSetupScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 3: Retry fallback - advance when a run fails */}
        <TransitionSeries.Sequence durationInFrames={220}>
          <AgentRouterFallbackScene />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
