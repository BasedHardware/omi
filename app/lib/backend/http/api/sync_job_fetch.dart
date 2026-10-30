part of 'conversations.dart';

class SyncJobFetch {
  final SyncJobFetchOutcome outcome;
  final SyncJobStatusResponse? status;
  final SyncRateLimitedException? rateLimit;
  final bool pollAdmitted;
  final bool missingConfirmationPending;

  const SyncJobFetch(this.outcome, [this.status])
      : rateLimit = null,
        pollAdmitted = true,
        missingConfirmationPending = false;

  const SyncJobFetch.throttled(this.rateLimit)
      : outcome = SyncJobFetchOutcome.throttled,
        status = null,
        pollAdmitted = true,
        missingConfirmationPending = false;

  /// A local cadence/budget decision, with no fetcher invocation.
  const SyncJobFetch.deferred()
      : outcome = SyncJobFetchOutcome.transient,
        status = null,
        rateLimit = null,
        pollAdmitted = false,
        missingConfirmationPending = false;

  /// A real 404/403 still awaiting the existing confirmation window.
  const SyncJobFetch.missingConfirmation()
      : outcome = SyncJobFetchOutcome.transient,
        status = null,
        rateLimit = null,
        pollAdmitted = true,
        missingConfirmationPending = true;
}
