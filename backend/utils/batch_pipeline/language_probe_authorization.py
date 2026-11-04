"""Per-dispatch authority for serving intake's optional language probes."""

from enum import Enum

from database.batch_pipeline_privacy import BatchPrivacyBlocked


class ProbeDecision(str, Enum):
    ALLOWED = 'allowed'
    PROBE_SKIPPED = 'probe_skipped'
    REFUSED = 'refused'


class LanguageProbeDenied(RuntimeError):
    """No success acknowledgement: the caller retains its accepted source."""


class ServingLanguageProbeGuard:
    def __init__(self, store, item, *, authorize):
        self.store, self.item, self.authorize = store, item, authorize
        self.decision: ProbeDecision | None = None
        self.privacy_error: BatchPrivacyBlocked | None = None

    def __call__(self):
        from utils.funded_processing import consent_allows
        from utils.stt_cap_dispatch import sync_allowed

        if self.decision in {ProbeDecision.PROBE_SKIPPED, ProbeDecision.REFUSED}:
            return False
        try:
            # Never share the initial intake snapshot or a prior probe's read.
            self.authorize(self.store, self.item, snapshots={})
            if not consent_allows(self.item.owner_id):
                self.decision = ProbeDecision.REFUSED
                return False
        except BatchPrivacyBlocked as error:
            self.privacy_error = error
            self.decision = ProbeDecision.REFUSED
            return False
        except Exception:
            self.decision = ProbeDecision.REFUSED
            return False
        try:
            allowed = sync_allowed(self.item.owner_id, self.item.duration_seconds, 'modulate', lane='batch')
        except Exception:
            allowed = False
        if not allowed:
            # A cap cannot strand ingestion. Skip optional LID and preserve the
            # ordinary unknown-language admission/compute-funding boundary.
            # A consent reset during the funding check still refuses custody.
            try:
                self.decision = (
                    ProbeDecision.PROBE_SKIPPED if consent_allows(self.item.owner_id) else ProbeDecision.REFUSED
                )
            except Exception:
                self.decision = ProbeDecision.REFUSED
            return False
        self.decision = ProbeDecision.ALLOWED
        return allowed

    def raise_if_denied(self):
        # The resolver treats provider/callback errors as unavailable. Restore
        # the denial before staging/admission, rather than acknowledging silence.
        if self.privacy_error is not None:
            raise self.privacy_error
        if self.decision is ProbeDecision.REFUSED:
            raise LanguageProbeDenied('batch language probe authorization denied')
