// "New" pill for a memory created in the last minute. Mac renders this in purple;
// per INV-UI-1 (no purple anywhere) it maps to the app's neutral primary — a
// white glyph on a faint white fill — same substitution used across the port.
export function NewBadge(): React.JSX.Element {
  return (
    <span className="inline-flex items-center rounded-full bg-white/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
      New
    </span>
  )
}
