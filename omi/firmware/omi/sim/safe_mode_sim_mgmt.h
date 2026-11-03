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
#endif
