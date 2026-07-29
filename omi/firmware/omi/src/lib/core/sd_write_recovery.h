#ifndef SD_WRITE_RECOVERY_H
#define SD_WRITE_RECOVERY_H

#include <stdbool.h>
#include <stdint.h>

#define SD_WRITE_RETRIES_PER_MOUNT 5U
#define SD_WRITE_MAX_REMOUNTS 2U

typedef enum {
    SD_WRITE_RECOVERY_HEALTHY = 0,
    SD_WRITE_RECOVERY_DEGRADED,
    SD_WRITE_RECOVERY_TERMINAL,
} sd_write_recovery_state_t;

typedef enum {
    SD_WRITE_RECOVERY_ACTION_RETRY = 0,
    SD_WRITE_RECOVERY_ACTION_REMOUNT,
    SD_WRITE_RECOVERY_ACTION_TERMINAL,
} sd_write_recovery_action_t;

typedef enum {
    SD_BOOT_MOUNT_READY = 0,
    SD_BOOT_MOUNT_REMOUNT,
    SD_BOOT_MOUNT_TERMINAL,
} sd_boot_mount_outcome_t;

typedef struct {
    sd_write_recovery_state_t state;
    uint8_t failures_on_mount;
    uint8_t remounts;
} sd_write_recovery_policy_t;

void sd_write_recovery_init(sd_write_recovery_policy_t *policy);
sd_write_recovery_action_t sd_write_recovery_on_failure(sd_write_recovery_policy_t *policy);
void sd_write_recovery_on_success(sd_write_recovery_policy_t *policy);
bool sd_write_recovery_is_terminal(const sd_write_recovery_policy_t *policy);
bool sd_write_recovery_mount_required(bool dirty, bool mounted, const sd_write_recovery_policy_t *policy);
/**
 * Consume one full boot mount result. A failed sd_mount() has already
 * exhausted the controller's per-mount attempts, so each failure advances one
 * bounded remount epoch rather than nesting another unbounded retry loop.
 */
sd_boot_mount_outcome_t sd_write_recovery_boot_mount_result(sd_write_recovery_policy_t *policy, int mount_result);

#endif
