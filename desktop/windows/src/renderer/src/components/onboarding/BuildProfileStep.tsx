import { useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { OrbitScanner } from './OrbitScanner'
import { runAppIndexing } from '../../lib/appMemories'
import { rankApps } from '../../lib/appSelection'
import { addAppNodes } from '../../lib/onboardingGraph'

type BuildProfileStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip?: () => void
}

type Phase = 'idle' | 'scanning' | 'done' | 'error'

/**
 * "Discovery" onboarding step. Local file indexing is privacy-sensitive, so it
 * stays idle until the user explicitly starts it.
 */
export function BuildProfileStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: BuildProfileStepProps): React.JSX.Element {
  const [phase, setPhase] = useState<Phase>('idle')
  const [fileCount, setFileCount] = useState<number | null>(null)

  const startScan = (): void => {
    if (phase === 'scanning') return
    setPhase('scanning')
    setFileCount(null)
    void runScan()
      .then((count) => {
        setFileCount(count)
        setPhase('done')
      })
      .catch(() => {
        setFileCount(null)
        setPhase('error')
      })
  }

  const statusLabel =
    phase === 'idle'
      ? 'Discovery is off'
      : phase === 'scanning'
        ? 'Scanning your projects and apps'
        : phase === 'done'
          ? 'Your workspace is mapped'
          : 'Discovery did not finish'
  const countLabel =
    phase === 'idle'
      ? 'No files indexed'
      : phase === 'error'
        ? 'Continue without scanning'
        : fileCount == null
          ? ' '
          : `${fileCount.toLocaleString()} files indexed`

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      align="left"
      eyebrow="DISCOVERY"
      title="Start building your profile"
      subtitle="Omi can scan projects and recent files when you choose."
      onContinue={phase === 'scanning' ? undefined : onContinue}
      onSkip={onSkip}
    >
      <div className="flex w-full flex-col items-center gap-4 rounded-2xl border border-white/5 bg-white/[0.03] px-6 py-8">
        <div className={phase === 'idle' || phase === 'error' ? 'opacity-45' : ''}>
          <OrbitScanner />
        </div>
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="text-sm font-medium text-white/85">{statusLabel}</p>
          <p className="text-xs text-white/40">{countLabel}</p>
        </div>
        {phase !== 'scanning' && (
          <button type="button" onClick={startScan} className="btn-ghost mt-2">
            {phase === 'done' ? 'Scan again' : 'Scan my workspace'}
          </button>
        )}
      </div>
    </StepScaffold>
  )
}

// Kick off the local file index and report how many files were indexed.
async function runScan(): Promise<number> {
  const api = window.omi as { indexFilesScan?: typeof window.omi.indexFilesScan }
  if (!api.indexFilesScan) {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    return 0
  }
  const status = await window.omi.indexFilesScan()
  try {
    const apps = await window.omi.indexFilesApps(200)
    await addAppNodes(rankApps(apps).map((a) => ({ name: a.name })))
  } catch {
    /* ignore - graph just won't gain app nodes */
  }
  void runAppIndexing().catch(() => {})
  return status.filesIndexed
}
