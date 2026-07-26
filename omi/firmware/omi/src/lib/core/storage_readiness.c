#include "storage_readiness.h"

storage_readiness_action_t storage_readiness_decide(bool media_ready,
                                                    bool snapshot_ready,
                                                    bool storage_terminal,
                                                    bool deadline_started,
                                                    bool deadline_expired)
{
    if (storage_terminal && !media_ready) {
        return STORAGE_READINESS_TERMINAL;
    }

    if (media_ready && (snapshot_ready || storage_terminal)) {
        return STORAGE_READINESS_SERVE;
    }

    if (!deadline_started) {
        return STORAGE_READINESS_WAKE_AND_WAIT;
    }

    if (deadline_expired) {
        return STORAGE_READINESS_RETRYABLE_TIMEOUT;
    }

    return STORAGE_READINESS_WAIT;
}
