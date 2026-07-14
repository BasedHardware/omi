import { useEffect, useState } from 'react'
import {
  getPreferences,
  setPreferences,
  completeOnboarding,
  setPendingRoute
} from '../lib/preferences'
import { clampOnboardingStep } from '../lib/onboardingProgress'
import { syncLanguage, setDisplayName } from '../lib/userProfile'
import { resolveLanguageCode, languageLabel } from '../lib/languages'
import { trackHowDidYouHear } from '../lib/analytics'
import { toast } from '../lib/toast'
import { NameStep } from '../components/onboarding/NameStep'
import { LanguageStep } from '../components/onboarding/LanguageStep'
import { HowDidYouHearStep } from '../components/onboarding/HowDidYouHearStep'
import { TrustStep } from '../components/onboarding/TrustStep'
import { BackgroundPrivacyStep } from '../components/onboarding/BackgroundPrivacyStep'
import { ScreenPermissionStep } from '../components/onboarding/ScreenPermissionStep'
import { BuildProfileStep } from '../components/onboarding/BuildProfileStep'
import { MicPermissionStep } from '../components/onboarding/MicPermissionStep'
import { AutomationPermissionStep } from '../components/onboarding/AutomationPermissionStep'
import { ShortcutSetupStep } from '../components/onboarding/ShortcutSetupStep'
import { VoiceIntroStep } from '../components/onboarding/VoiceIntroStep'
import { AskDemoStep } from '../components/onboarding/AskDemoStep'
import { GoalStep } from '../components/onboarding/GoalStep'
import { AutoCreatedTasksStep } from '../components/onboarding/AutoCreatedTasksStep'
import { createGoal } from '../lib/goals'
// Import BrainGraph DIRECTLY (not via LazyBrainGraph) for onboarding — matches
// the f42497b version that rendered reliably. The lazy wrapper's Suspense +
// ErrorBoundary was silently swallowing the onboarding map to a blank pane. The
// Memories tab still uses LazyBrainGraph (lazy + scoping + pauseWhenHidden); this
// only changes onboarding.
import { BrainGraph } from '../components/graph/BrainGraph'
import {
  initOnboardingGraph,
  addUserNode,
  addLanguageNode,
  useOnboardingGraph
} from '../lib/onboardingGraph'

const TOTAL_STEPS = 14

export function Onboarding(): React.JSX.Element {
  // Resume where the user left off if they quit mid-onboarding. Clamped in case
  // the step list changed between app versions.
  const [step, setStep] = useState(() =>
    clampOnboardingStep(getPreferences().onboardingStep, TOTAL_STEPS)
  )
  const prefs = getPreferences()

  // A FRESH onboarding start clears any prior local graph so the reveal begins
  // empty (mirrors the macOS "clear graph on first onboarding start"); a RESUME
  // hydrates the persisted one instead. Onboarding re-mounts whenever the
  // renderer reloads (the main process reloads a crashed renderer) or the app is
  // relaunched mid-wizard, and it comes back at the saved step — clearing on
  // those mounts wiped the `user` node written by the name step, which took the
  // user off their own map and orphaned every edge (they all anchor at `user`),
  // leaving a map of unconnected dots. Reads prefs directly so this stays a
  // mount-only effect.
  useEffect(() => {
    const p = getPreferences()
    void initOnboardingGraph(clampOnboardingStep(p.onboardingStep, TOTAL_STEPS), p.displayName)
  }, [])

  // Persist the current step so a quit-and-relaunch resumes here. Cleared when
  // onboarding completes (completeOnboarding) or is reset (resetOnboarding).
  useEffect(() => {
    setPreferences({ onboardingStep: step })
  }, [step])

  const graph = useOnboardingGraph()

  const next = (): void => setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1))
  const back = (): void => setStep((s) => Math.max(s - 1, 0))

  const handleName = (name: string): void => {
    setPreferences({ displayName: name })
    void addUserNode(name)
    // Best-effort: also set the Firebase displayName (no backend name endpoint).
    void setDisplayName(name).catch(() => {
      toast('Could not sync your name', { tone: 'warn' })
    })
    next()
  }

  const handleLanguage = (language: string): void => {
    // The "Other" step passes free-text (e.g. "Spanish"); normalize to the ISO
    // code the rest of the app expects (v4/listen URL, backend sync, Settings).
    const code = resolveLanguageCode(language)
    setPreferences({ language: code })
    void addLanguageNode(code, languageLabel(code))
    void syncLanguage(code).catch(() => {
      toast('Saved locally — language sync will retry later', { tone: 'warn' })
    })
    next()
  }

  const handleHowDidYouHear = (source: string): void => {
    trackHowDidYouHear(source)
    next()
  }

  const handleGoal = (goal: string): void => {
    setPreferences({ goal })
    // Best-effort sync to the Omi goals backend — never block onboarding on the
    // network. Advance to the final "auto-created tasks" screen.
    void createGoal(goal).catch(() => {
      toast('Saved locally — goal sync will retry later', { tone: 'warn' })
    })
    next()
  }

  // Finish onboarding and land on the Tasks tab. We record the destination
  // first, then flip the gate flag — the app shell consumes the pending route on
  // mount (navigating from here directly races the gate's redirect to /home).
  const finishToTasks = (): void => {
    setPendingRoute('/tasks')
    completeOnboarding()
  }

  // App names already revealed in the brain map (id prefix `app_`), used to
  // personalize the AI-generated goal suggestion.
  const appNames = graph.nodes.filter((n) => n.id.startsWith('app_')).map((n) => n.label)

  // The active step's card. Only this swaps as the user advances — the Brain Map
  // in the shell below stays mounted, so it never re-runs its reveal animation;
  // it only updates when a choice on the left actually changes the graph.
  const renderStep = (): React.JSX.Element => {
    if (step === 0) {
      return (
        <NameStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          initialValue={prefs.displayName ?? ''}
          onContinue={handleName}
        />
      )
    }
    if (step === 1) {
      return (
        <LanguageStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          initialValue={prefs.language}
          onContinue={handleLanguage}
          onBack={back}
        />
      )
    }
    if (step === 2) {
      return (
        <HowDidYouHearStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          onContinue={handleHowDidYouHear}
          onBack={back}
        />
      )
    }
    if (step === 3) {
      return <TrustStep stepIndex={step} totalSteps={TOTAL_STEPS} onContinue={next} onBack={back} />
    }
    if (step === 4) {
      // Background/privacy consent: always-on listening, tray residence, and
      // launch-at-login, established up front for this tray-resident companion.
      return <BackgroundPrivacyStep stepIndex={step} totalSteps={TOTAL_STEPS} onContinue={next} />
    }
    if (step === 5) {
      return (
        <ScreenPermissionStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          onContinue={next}
          onSkip={next}
        />
      )
    }
    if (step === 6) {
      // The old DiskAccessStep (button-driven file scan) is hidden; this
      // discovery step scans automatically with the orbit animation instead.
      return (
        <BuildProfileStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          onContinue={next}
          onSkip={next}
        />
      )
    }
    if (step === 7) {
      return (
        <MicPermissionStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          onContinue={next}
          onSkip={next}
        />
      )
    }
    if (step === 8) {
      return (
        <AutomationPermissionStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          onContinue={next}
          onSkip={next}
        />
      )
    }
    if (step === 9) {
      // Floating-bar shortcut setup: enables + warms the overlay so the user can
      // test the press here, then advances to the voice intro.
      return (
        <ShortcutSetupStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          onContinue={next}
          onSkip={next}
        />
      )
    }
    if (step === 10) {
      return (
        <VoiceIntroStep stepIndex={step} totalSteps={TOTAL_STEPS} onContinue={next} onSkip={next} />
      )
    }
    if (step === 11) {
      // Ask demo: type a question in the bar → Omi's answer (Mac comparison)
      // reveals, then advances to the goal step.
      return (
        <AskDemoStep stepIndex={step} totalSteps={TOTAL_STEPS} onContinue={next} onSkip={next} />
      )
    }
    if (step === 12) {
      return (
        <GoalStep
          stepIndex={step}
          totalSteps={TOTAL_STEPS}
          apps={appNames}
          onContinue={handleGoal}
          onSkip={next}
        />
      )
    }
    // Final screen: a preview of the auto-created tasks feature. Its button both
    // completes onboarding and routes straight to the Tasks tab.
    return <AutoCreatedTasksStep onFinish={finishToTasks} />
  }

  // Persistent two-pane shell: omi logo + the swapping step card on the left, the
  // single always-mounted Brain Map on the right. Keeping the graph here (rather
  // than inside each step) is what stops it from glitching/restarting on every
  // navigation — only its data changes as the graph grows.
  // Steps that show the step card centered on the whole screen with NO brain
  // map: the name screen (0), the "I'm going to ask you for a few permissions"
  // screen (3, TrustStep), the background/privacy consent screen (4), the
  // floating-bar steps (9 shortcut, 10 voice, 11 ask demo), and the final
  // auto-created-tasks screen (13). The Goal step (12) keeps the map (it
  // personalizes its suggestion from the revealed app nodes). The map is only
  // hidden (display:none), never unmounted, so it persists and returns smoothly
  // on the next steps.
  const hideBrainMap =
    step === 0 ||
    step === 3 ||
    step === 4 ||
    step === 9 ||
    step === 10 ||
    step === 11 ||
    step === 13

  return (
    <div className="app-canvas relative flex h-full">
      <div className="flex flex-1 items-center justify-center p-8">{renderStep()}</div>
      <div
        className={
          hideBrainMap
            ? 'hidden'
            : 'flex flex-1 items-center justify-center border-l border-white/5 p-8'
        }
      >
        {/* Sized container for the brain map. The graph fills this box (and is
            framed to it), so its on-screen size is controlled here: change the
            max-h value to make it expand more or less. */}
        <div className="relative aspect-square h-full max-h-[760px] max-w-full -translate-x-8">
          <BrainGraph graph={graph} centerNodeId="user" interactive={false} shuffleKey={step} />
        </div>
      </div>
    </div>
  )
}
