import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import {
  usePostSetupHomeCue,
  type PostSetupHomeCue,
} from '../src/app/usePostSetupHomeCue';
import type {ReadsPhase} from '../src/app/useDesktopReads';

function Harness({
  onboardingRequired,
  onState,
  readsPhase,
}: {
  onboardingRequired: boolean | null;
  onState: (cue: PostSetupHomeCue) => void;
  readsPhase: ReadsPhase;
}) {
  const cue = usePostSetupHomeCue(onboardingRequired, readsPhase);
  onState(cue);
  return null;
}

async function renderCue(
  onboardingRequired: boolean | null,
  readsPhase: ReadsPhase,
) {
  let latest: PostSetupHomeCue = null;
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(
      <Harness
        onboardingRequired={onboardingRequired}
        onState={cue => {
          latest = cue;
        }}
        readsPhase={readsPhase}
      />,
    );
  });
  return {
    latest: () => latest,
    update: async (nextOnboarding: boolean | null, nextReads: ReadsPhase) => {
      await ReactTestRenderer.act(async () => {
        renderer.update(
          <Harness
            onboardingRequired={nextOnboarding}
            onState={cue => {
              latest = cue;
            }}
            readsPhase={nextReads}
          />,
        );
      });
    },
  };
}

test('cold probe ready does not invent a Home prove-it cue', async () => {
  const hook = await renderCue(null, 'initial-loading');
  expect(hook.latest()).toBeNull();
  await hook.update(false, 'ready');
  expect(hook.latest()).toBeNull();
});

test('leaving Welcome arms prove-it only after reads settle ready', async () => {
  const hook = await renderCue(true, 'initial-loading');
  expect(hook.latest()).toBeNull();

  await hook.update(false, 'initial-loading');
  expect(hook.latest()).toBeNull();

  await hook.update(false, 'ready');
  expect(hook.latest()).toBe('proven');
});

test('post-setup unavailable settles honestly without a prove-it cue', async () => {
  const hook = await renderCue(true, 'initial-loading');
  await hook.update(false, 'refreshing');
  expect(hook.latest()).toBeNull();
  await hook.update(false, 'unavailable');
  expect(hook.latest()).toBe('unavailable');
});

test('returning to Welcome clears a prior prove-it cue', async () => {
  const hook = await renderCue(true, 'initial-loading');
  await hook.update(false, 'ready');
  expect(hook.latest()).toBe('proven');
  await hook.update(true, 'ready');
  expect(hook.latest()).toBeNull();
});
