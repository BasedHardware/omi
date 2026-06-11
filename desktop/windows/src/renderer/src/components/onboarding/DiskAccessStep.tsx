import { HardDrive } from 'lucide-react'
import { PermissionStep } from './PermissionStep'
import { runAppIndexing } from '../../lib/appMemories'
import { rankApps } from '../../lib/appSelection'
import { addAppNodes } from '../../lib/onboardingGraph'

type DiskAccessStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  onContinue: () => void
}

export function DiskAccessStep({
  stepIndex,
  totalSteps,
  aside,
  onContinue
}: DiskAccessStepProps): React.JSX.Element {
  // Kick off the local file index. The backend (indexFilesScan) ships on a
  // separate branch; call it when present, otherwise simulate so onboarding still
  // flows. Narrow inline cast avoids depending on the shared preload type here.
  const runScan = async (): Promise<void> => {
    const api = window.omi as { indexFilesScan?: () => Promise<unknown> }
    if (api.indexFilesScan) {
      try {
        await api.indexFilesScan()
        // Reveal purple "thing" nodes for the apps the user has, with clean
        // names — the macOS onboarding moment. Best-effort; never blocks.
        try {
          const apps = await window.omi.indexFilesApps(200)
          await addAppNodes(rankApps(apps).map((a) => ({ name: a.name })))
        } catch {
          /* ignore — graph just won't gain app nodes */
        }
        // Fire-and-forget: turn the freshly indexed apps into "Uses <App>"
        // memories + trigger the KG rebuild. runAppIndexing swallows its own
        // errors; never block onboarding on it.
        void runAppIndexing().catch(() => {})
        return
      } catch {
        /* fall through to the simulated delay below */
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }

  return (
    <PermissionStep
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      aside={aside}
      eyebrow="ACCESS"
      title="Let Omi scan your work"
      subtitle="File access lets Omi map your projects and files"
      icon={<HardDrive className="h-5 w-5 text-white/60" />}
      cardLabel="File Access"
      statusText={{
        idle: 'Not scanned yet',
        waiting: 'Scanning your files',
        granted: 'Indexed'
      }}
      buttonLabel={{
        idle: 'Disk Access',
        waiting: 'Scanning…',
        granted: 'Indexed'
      }}
      onActivate={runScan}
      onContinue={onContinue}
    />
  )
}
