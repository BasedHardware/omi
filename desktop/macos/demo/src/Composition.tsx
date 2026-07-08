import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { AbsoluteFill } from "remotion";
import { IntroScene } from "./scenes/IntroScene";
import { ScreenMonitorScene } from "./scenes/ScreenMonitorScene";
import { AudioListenScene } from "./scenes/AudioListenScene";
import { ProactiveAdviceScene } from "./scenes/ProactiveAdviceScene";
import { TaskExtractionScene } from "./scenes/TaskExtractionScene";
import { FocusScene } from "./scenes/FocusScene";
import { IntegrationsScene } from "./scenes/IntegrationsScene";
import { OutroScene } from "./scenes/OutroScene";

export const MyComposition = () => {
  const transitionDuration = 20;

  return (
    <AbsoluteFill style={{ background: "#0a0a0a" }}>
      <TransitionSeries>
        {/* Scene 1: Intro - Meet Omi */}
        <TransitionSeries.Sequence durationInFrames={90}>
          <IntroScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 2: Screen Monitoring */}
        <TransitionSeries.Sequence durationInFrames={120}>
          <ScreenMonitorScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-right" })}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 3: Audio Listening & Transcription */}
        <TransitionSeries.Sequence durationInFrames={140}>
          <AudioListenScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 4: Proactive Advice */}
        <TransitionSeries.Sequence durationInFrames={120}>
          <ProactiveAdviceScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-bottom" })}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 5: Task Extraction */}
        <TransitionSeries.Sequence durationInFrames={120}>
          <TaskExtractionScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 6: Focus Tracking */}
        <TransitionSeries.Sequence durationInFrames={120}>
          <FocusScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={slide({ direction: "from-left" })}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 7: Integrations */}
        <TransitionSeries.Sequence durationInFrames={120}>
          <IntegrationsScene />
        </TransitionSeries.Sequence>

        <TransitionSeries.Transition
          presentation={fade()}
          timing={linearTiming({ durationInFrames: transitionDuration })}
        />

        {/* Scene 8: Outro / CTA */}
        <TransitionSeries.Sequence durationInFrames={90}>
          <OutroScene />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
