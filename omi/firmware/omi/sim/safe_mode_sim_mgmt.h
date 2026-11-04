/* Link seam only. Values/signature mirror the pinned Zephyr callbacks.h.
 * No SMP protocol or radio is simulated. */
#ifndef OMI_SAFE_MODE_SIM_MGMT_H
#define OMI_SAFE_MODE_SIM_MGMT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
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
#define FIXED_PARTITION_ID(label) 1
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

#endif
