/** Small right-aligned hotkey hint rendered as dimmed kbd chips. */
export function Shortcut(props: { keys: string[] }): React.JSX.Element {
  return (
    <span className="flex shrink-0 items-center gap-1">
      {props.keys.map((k) => (
        <kbd
          key={k}
          className="rounded border border-white/15 bg-white/5 px-1.5 py-0.5 font-sans text-[10px] font-medium leading-none text-white/50"
        >
          {k}
        </kbd>
      ))}
    </span>
  )
}
