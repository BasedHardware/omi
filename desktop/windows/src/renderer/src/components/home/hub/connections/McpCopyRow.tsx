import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import type { McpCloudCopyRow } from '../../../../../../shared/mcpExports'

// One copy-row on the assisted cloud-connector guide card: a label, the value in
// a monospace field, and a copy button. A `blank` field (e.g. the client secret)
// shows a muted "Leave blank" with nothing to copy — mirrors macOS's guidance
// overlay, which renders empty required fields as "leave blank".
export function McpCopyRow({ row }: { row: McpCloudCopyRow }): React.JSX.Element {
  const [copied, setCopied] = useState(false)

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(row.value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      /* clipboard denied — the value is still visible to copy by hand */
    }
  }

  return (
    <div className="flex items-center gap-3 py-2">
      <span className="w-[130px] shrink-0 text-[12.5px] font-medium text-home-muted">
        {row.label}
      </span>
      {row.blank ? (
        <span className="flex-1 text-[13px] italic text-home-faint">Leave blank</span>
      ) : (
        <>
          <code className="min-w-0 flex-1 truncate rounded-md bg-white/[0.04] px-2 py-1 font-mono text-[12px] text-home-ink">
            {row.value}
          </code>
          <button
            type="button"
            onClick={copy}
            aria-label={`Copy ${row.label}`}
            className="focus-ring flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-home-muted transition-colors hover:bg-white/10 hover:text-home-ink"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" strokeWidth={2.25} />
            ) : (
              <Copy className="h-3.5 w-3.5" strokeWidth={2} />
            )}
          </button>
        </>
      )}
    </div>
  )
}
