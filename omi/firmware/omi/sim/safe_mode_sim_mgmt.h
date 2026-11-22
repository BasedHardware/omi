/* Link seam only. Values/signature mirror the pinned Zephyr callbacks.h.
 * No SMP protocol or radio is simulated. */
#ifndef OMI_SAFE_MODE_SIM_MGMT_H
#define OMI_SAFE_MODE_SIM_MGMT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#if defined(CONFIG_FLASH_MAP) && !defined(OMI_SAFE_MODE_HOST)
/* native_sim: the real partition map (slot1 exists in the board DTS). */
#include <zephyr/storage/flash_map.h>
#endif
enum mgmt_cb_return { MGMT_CB_OK, MGMT_CB_ERROR_RC, MGMT_CB_ERROR_ERR };
#define MGMT_EVT_OP_IMG_MGMT_DFU_PENDING ((3u << 16) | (1u << 3))
struct mgmt_callback {
    enum mgmt_cb_return (*callback)(uint32_t, enum mgmt_cb_return, int32_t *, uint16_t *, bool *, void *, size_t);
    uint32_t event_id;
};
void mgmt_callback_register(struct mgmt_callback *callback);

/* Only callback fields used by production code; native_sim has no mcumgr. */
#define MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK ((3u << 16) | (1u << 0))
#define MGMT_EVT_OP_IMG_MGMT_DFU_STOPPED ((3u << 16) | (1u << 1))
#define MGMT_ERR_EINVAL 3
#ifndef FIXED_PARTITION_ID
#define FIXED_PARTITION_ID(label) 1
#endif
struct img_mgmt_upload_req {
    uint32_t image;
};
struct img_mgmt_upload_action {
    int area_id;
};
struct img_mgmt_upload_check {
    struct img_mgmt_upload_action *action;
    struct img_mgmt_upload_req *req;
};

#if defined(CONFIG_OMI_NATIVE_SIM) && !defined(OMI_SAFE_MODE_HOST)
/* Simulator power model (sim/sim_power.c): a fatal error ends this simulated
 * boot as a warm software reset that keeps retained RAM. */
FUNC_NORETURN void omi_sim_reset_fatal(void);
#endif

#endif
