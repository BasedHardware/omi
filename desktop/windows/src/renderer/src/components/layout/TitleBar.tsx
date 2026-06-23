export function TitleBar(): React.JSX.Element {
  return (
    <div
      className="fixed left-0 right-0 top-0 z-[9999] h-8 select-none"
      style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
    />
  )
}
