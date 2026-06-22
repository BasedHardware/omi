// The body of a single onboarding step: a column holding a progress bar, an
// optional eyebrow, title, body, Back, and primary Continue button. Steps render
// their own body as children. The page frame (omi logo, background, and the
// persistent Brain Map on the right) is owned by the Onboarding shell, so this
// component renders only the card. The `aside` prop is accepted for backwards
// compatibility but no longer rendered here — the Brain Map lives in the shell.

type StepScaffoldProps = {
  stepIndex: number
  totalSteps: number
  title: string
  eyebrow?: string
  subtitle?: string
  /** Override the subtitle's color/emphasis (default is muted white/50). */
  subtitleClassName?: string
  /** Override the card's max-width (default 'max-w-[400px]'); wider for steps
   *  with large media. */
  widthClassName?: string
  continueLabel?: string
  continueDisabled?: boolean
  onContinue?: () => void
  onBack?: () => void
  /** When set, a small grey "Skip" text button is shown at the right edge of the
   *  progress-bar row (used to skip optional permission steps). */
  onSkip?: () => void
  align?: 'center' | 'left'
  children?: React.ReactNode
  aside?: React.ReactNode
}

export function StepScaffold({
  stepIndex,
  totalSteps,
  title,
  eyebrow,
  subtitle,
  subtitleClassName,
  widthClassName = 'max-w-[400px]',
  continueLabel = 'Continue',
  continueDisabled = false,
  onContinue,
  onBack,
  onSkip,
  align = 'center',
  children
}: StepScaffoldProps): React.JSX.Element {
  const left = align === 'left'
  const progressJustify = onSkip ? 'justify-between' : left ? 'justify-start' : 'justify-center'
  return (
    <div
      className={
        'animate-fade-in relative z-10 flex w-full flex-col ' +
        widthClassName +
        ' ' +
        (left ? 'items-start text-left' : 'items-center text-center')
      }
    >
      <div className={'mb-8 flex w-full items-center ' + progressJustify}>
        <div className="flex gap-1.5">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <span
              key={i}
              className={
                'h-1.5 rounded-full transition-all ' +
                (i === stepIndex
                  ? 'w-5 bg-white'
                  : i < stepIndex
                    ? 'w-1.5 bg-white'
                    : 'w-1.5 bg-white/20')
              }
            />
          ))}
        </div>
        {onSkip && (
          <button
            type="button"
            onClick={onSkip}
            className="text-xs text-white/40 transition-colors hover:text-white/70"
          >
            Skip
          </button>
        )}
      </div>

      {eyebrow && (
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-white/40">{eyebrow}</p>
      )}
      <h1 className="font-display text-3xl font-semibold text-white/95">{title}</h1>
      {subtitle && (
        <p className={'mt-2 text-sm leading-relaxed ' + (subtitleClassName ?? 'text-white/50')}>
          {subtitle}
        </p>
      )}

      {children && (
        <div className={'mt-6 flex w-full flex-col ' + (left ? 'items-start' : 'items-center')}>
          {children}
        </div>
      )}

      {(onContinue || onBack) && (
        <div className={'mt-8 flex items-center gap-3 ' + (left ? 'justify-start' : 'justify-center')}>
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="rounded-xl bg-white px-6 py-3 font-medium text-black transition-opacity hover:opacity-90"
            >
              Back
            </button>
          )}
          {onContinue && (
            <button
              type="button"
              onClick={onContinue}
              disabled={continueDisabled}
              className="rounded-xl bg-white px-8 py-3 font-medium text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {continueLabel}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
