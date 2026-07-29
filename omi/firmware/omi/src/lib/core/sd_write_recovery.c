#include "sd_write_recovery.h"

void sd_write_recovery_init(sd_write_recovery_policy_t *policy)
{
    if (!policy) {
        return;
    }

    policy->state = SD_WRITE_RECOVERY_HEALTHY;
    policy->failures_on_mount = 0U;
    policy->remounts = 0U;
}

sd_write_recovery_action_t sd_write_recovery_on_failure(sd_write_recovery_policy_t *policy)
{
    if (!policy || policy->state == SD_WRITE_RECOVERY_TERMINAL) {
        return SD_WRITE_RECOVERY_ACTION_TERMINAL;
    }

    policy->state = SD_WRITE_RECOVERY_DEGRADED;
    policy->failures_on_mount++;
    if (policy->failures_on_mount < SD_WRITE_RETRIES_PER_MOUNT) {
        return SD_WRITE_RECOVERY_ACTION_RETRY;
    }

    policy->failures_on_mount = 0U;
    if (policy->remounts < SD_WRITE_MAX_REMOUNTS) {
        policy->remounts++;
        return SD_WRITE_RECOVERY_ACTION_REMOUNT;
    }

    policy->state = SD_WRITE_RECOVERY_TERMINAL;
    return SD_WRITE_RECOVERY_ACTION_TERMINAL;
}

void sd_write_recovery_on_success(sd_write_recovery_policy_t *policy)
{
    sd_write_recovery_init(policy);
}

bool sd_write_recovery_is_terminal(const sd_write_recovery_policy_t *policy)
{
    return policy && policy->state == SD_WRITE_RECOVERY_TERMINAL;
}

bool sd_write_recovery_mount_required(bool dirty, bool mounted, const sd_write_recovery_policy_t *policy)
{
    return dirty && !mounted && !sd_write_recovery_is_terminal(policy);
}

sd_boot_mount_outcome_t sd_write_recovery_boot_mount_result(sd_write_recovery_policy_t *policy, int mount_result)
{
    if (mount_result == 0) {
        sd_write_recovery_on_success(policy);
        return SD_BOOT_MOUNT_READY;
    }

    /*
     * sd_mount() already exhausted SD_WRITE_RETRIES_PER_MOUNT controller
     * attempts. Advance to the next remount epoch in one production-seam step.
     */
    sd_write_recovery_action_t action = SD_WRITE_RECOVERY_ACTION_RETRY;
    while (action == SD_WRITE_RECOVERY_ACTION_RETRY) {
        action = sd_write_recovery_on_failure(policy);
    }

    return action == SD_WRITE_RECOVERY_ACTION_TERMINAL ? SD_BOOT_MOUNT_TERMINAL : SD_BOOT_MOUNT_REMOUNT;
}
