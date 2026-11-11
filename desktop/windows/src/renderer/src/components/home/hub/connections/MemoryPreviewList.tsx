// The reviewed-memories preview shared by the paste-import and sticky-notes rows:
// an optional italic profile summary above a scrollable bulleted list of the exact
// memories that will be written. Extracted so both flows render it identically.
export function MemoryPreviewList({
  profile,
  memories
}: {
  profile?: string
  memories: string[]
}): React.JSX.Element {
  return (
    <div className="space-y-2">
      {profile && (
        <p className="rounded-chip bg-black/20 px-3.5 py-2.5 text-[12.5px] italic text-home-muted">
          {profile}
        </p>
      )}
      {memories.length > 0 && (
        <ul className="rounded-chip max-h-36 overflow-y-auto bg-black/20 px-3.5 py-2.5 text-[12.5px] text-home-muted">
          {memories.map((m, i) => (
            <li key={i} className="py-0.5">
              • {m}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
