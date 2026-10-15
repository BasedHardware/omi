import type { UserSubscription } from '@/types/user';

/** The existing allowance is server authority, independent of a plan's paid status. */
export function TranscriptionUsageMeter({
  subscription,
}: {
  subscription: UserSubscription | null;
}) {
  const limit = subscription?.transcription_seconds_limit;
  const used = subscription?.transcription_seconds_used;
  const available =
    typeof limit === 'number' &&
    Number.isFinite(limit) &&
    limit >= 0 &&
    typeof used === 'number' &&
    Number.isFinite(used) &&
    used >= 0;
  const capped = available && limit > 0;
  const percent = capped ? Math.min(100, (used / limit) * 100) : 0;
  const hours = (seconds: number) => {
    const value = seconds / 3600;
    // A positive balance under 0.05 h must not round to "0 h left" — that
    // tells a user with minutes remaining the allowance is already gone.
    if (seconds > 0 && value < 0.05) return '<0.1 h';
    return `${value.toLocaleString(undefined, {
      maximumFractionDigits: 1,
    })} h`;
  };

  return (
    <section
      aria-label="Monthly listening"
      className="mb-6 rounded-xl border border-bg-quaternary p-4"
    >
      <h4 className="mb-2 text-sm font-semibold text-text-secondary">
        Monthly listening
      </h4>
      {!available ? (
        <p className="text-sm text-text-tertiary">Listening allowance unavailable</p>
      ) : (
        <>
          <p className="text-lg font-semibold text-text-primary">
            {hours(used)} used
            {capped ? ` of ${hours(limit)}` : ' · No monthly listening cap'}
          </p>
          {capped && (
            <>
              <p className="mb-2 text-sm text-text-tertiary">
                {hours(Math.max(0, limit - used))} left
              </p>
              <div
                role="progressbar"
                aria-label="Monthly listening used"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
                className="h-2.5 overflow-hidden rounded-full bg-bg-quaternary"
              >
                <div
                  className="h-full rounded-full bg-text-secondary"
                  style={{ width: `${percent}%` }}
                />
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
