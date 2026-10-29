"""Per-dispatch authority for serving intake's optional language probes."""

from database.batch_pipeline_privacy import BatchPrivacyBlocked


class LanguageProbeDenied(RuntimeError):
    """No success acknowledgement: the caller retains its accepted source."""


class ServingLanguageProbeGuard:
    def __init__(self, store, item, *, authorize):
        self.store, self.item, self.authorize = store, item, authorize
        self.denied = False
        self.privacy_error: BatchPrivacyBlocked | None = None

    def __call__(self):
        from utils.funded_processing import consent_allows
        from utils.stt_cap_dispatch import sync_allowed

        if self.denied:
            return False
        try:
            # Never share the initial intake snapshot or a prior probe's read.
            self.authorize(self.store, self.item, snapshots={})
            allowed = consent_allows(self.item.owner_id) and sync_allowed(
                self.item.owner_id, self.item.duration_seconds, 'modulate', lane='batch'
            )
        except BatchPrivacyBlocked as error:
            self.privacy_error = error
            allowed = False
        except Exception:
            allowed = False
        self.denied = not allowed
        return allowed

    def raise_if_denied(self):
        # The resolver treats provider/callback errors as unavailable. Restore
        # the denial before staging/admission, rather than acknowledging silence.
        if self.privacy_error is not None:
            raise self.privacy_error
        if self.denied:
            raise LanguageProbeDenied('batch language probe authorization denied')
