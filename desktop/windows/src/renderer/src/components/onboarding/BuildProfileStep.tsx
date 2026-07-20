import { useEffect, useRef, useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { OrbitScanner } from './OrbitScanner'
import { runAppIndexing } from '../../lib/appMemories'
import { rankApps } from '../../lib/appSelection'
import { addAppNodes, addWorkspaceNodes } from '../../lib/onboardingGraph'
import { native } from '../../lib/native'

type BuildProfileStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip?: () => void
}

type Phase = 'scanning' | 'done' | 'error'

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
  const [scanError, setScanError] = useState<string | null>(null)
  // Guard against React StrictMode's double-invoke so we only kick one scan.
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    void runScan().then(
      (count) => {
        setFileCount(count)
        setPhase('done')
      },
      (error) => {
        setScanError(error instanceof Error ? error.message : 'Omi could not index your files.')
        setPhase('error')
      }
    )
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
            {phase === 'scanning'
              ? 'Scanning your projects and apps'
              : phase === 'done'
                ? 'Your workspace is mapped'
                : 'Omi could not index your workspace'}
          </p>
          {/* Placeholder keeps the line's height before the count is known. */}
          <p className="text-xs text-white/40">
            {phase === 'error' ? scanError : fileCount == null ? ' ' : `${fileCount.toLocaleString()} files indexed`}
          </p>
        </div>
      </div>
    </StepScaffold>
  )
}

async function runScan(): Promise<number> {
  const status = await native.fileIndexScan()
  const digest = await native.kgFileIndexDigest()
  await addWorkspaceNodes(
    (digest.activeFolders.length ? digest.activeFolders : digest.topFolders)
      .map((folder) => folder.folder)
      .slice(0, 8)
  )
  const apps = await native.fileIndexApps(200)
  await addAppNodes(rankApps(apps).map((a) => ({ name: a.name })))
  await runAppIndexing()
  return status.filesIndexed
}
