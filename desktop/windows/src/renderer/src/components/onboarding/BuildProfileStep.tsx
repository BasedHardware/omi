import { useEffect, useRef, useState } from 'react'
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

type Phase = 'scanning' | 'done'

/**
 * "Discovery" onboarding step. Unlike the old disk-access step there's no
 * button — the file index kicks off automatically on mount. The orbit animation
 * runs while scanning; when the scan resolves we swap the label, reveal the real
 * indexed-file count, and surface the Continue button. The count line always
 * reserves its height (non-breaking space placeholder) so nothing shifts when
 * the number arrives.
 */
export function BuildProfileStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: BuildProfileStepProps): React.JSX.Element {
  const [phase, setPhase] = useState<Phase>('scanning')
  const [fileCount, setFileCount] = useState<number | null>(null)
  // Guard against React StrictMode's double-invoke so we only kick one scan.
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void runScan().then((count) => {
      setFileCount(count)
      setPhase('done')
    })
  }, [])

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      align="left"
      eyebrow="DISCOVERY"
      title="Start building your profile"
      subtitle="Omi scans projects and recent files"
      onContinue={phase === 'done' ? onContinue : undefined}
      onSkip={onSkip}
    >
      <div className="flex w-full flex-col items-center gap-4 rounded-2xl border border-white/5 bg-white/[0.03] px-6 py-8">
        <OrbitScanner />
        <div className="flex flex-col items-center gap-1 text-center">
          <p className="text-sm font-medium text-white/85">
            {phase === 'scanning' ? 'Scanning your projects and apps' : 'Your workspace is mapped'}
          </p>
          {/* Placeholder keeps the line's height before the count is known. */}
          <p className="text-xs text-white/40">
            {fileCount == null ? ' ' : `${fileCount.toLocaleString()} files indexed`}
          </p>
        </div>
      </div>
    </StepScaffold>
  )
}

// Kick off the local file index and report how many files were indexed. Mirrors
// the old disk-access step's side effects: reveal the user's app nodes on the
// brain map and fire the "Uses <App>" memory + KG rebuild. The backend may ship
// on a separate branch; if absent we simulate a delay so onboarding still flows.
async function runScan(): Promise<number> {
  const api = window.omi as { indexFilesScan?: typeof window.omi.indexFilesScan }
  if (api.indexFilesScan) {
    try {
      const status = await window.omi.indexFilesScan()
      try {
        const apps = await window.omi.indexFilesApps(200)
        await addAppNodes(rankApps(apps).map((a) => ({ name: a.name })))
      } catch {
        /* ignore — graph just won't gain app nodes */
      }
      void runAppIndexing().catch(() => {})
      return status.filesIndexed
    } catch {
      /* fall through to the simulated delay below */
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 1500))
  return 0
}
