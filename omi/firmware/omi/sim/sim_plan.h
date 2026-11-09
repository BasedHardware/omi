/* One simulated boot's pre-state and hardware timeline, shared by the
 * runner-side loader (host/sim_host.c, host libc) and the embedded side
 * (sim_power.c). Both sides are the same x86-64 process, so the layout is
 * plain fixed-width C. The scenario runner writes boot.cfg in the boot's cwd.
 */
#ifndef OMI_SIM_PLAN_H
#define OMI_SIM_PLAN_H
#include <stdint.h>

#define OMI_SIM_MAX_EVENTS 512
#define OMI_SIM_MAX_FAULTS 16
#define OMI_SIM_RETAINED_MAX 64

enum omi_sim_event_kind {
    OMI_SIM_EV_BUTTON = 1,  /* value: 1 pressed, 0 released */
    OMI_SIM_EV_CHARGER = 2, /* value: 1 charging (pin low), 0 not */
    OMI_SIM_EV_BATTERY_MV = 3,
    OMI_SIM_EV_PANIC = 4,     /* k_panic() from a sim thread: real fatal path */
    OMI_SIM_EV_CONNECTED = 5, /* value: 1 a central is connected, 0 not */
    OMI_SIM_EV_SD = 6,        /* value: omi_sim_sd_state */
    OMI_SIM_EV_APP_MUTE = 7,  /* capture_mute_set(value): the app's mute GATT write */
    OMI_SIM_EV_DFU = 8,       /* value: enum omi_sim_dfu_op, delivered to the mcumgr callback */
};

/* Image-management events an SMP client can cause (no SMP or radio is simulated). */
enum omi_sim_dfu_op {
    OMI_SIM_DFU_CHUNK_APP = 1,    /* chunk for image 0 into the application secondary slot */
    OMI_SIM_DFU_CHUNK_IMAGE1 = 2, /* chunk for image 1 (network core) */
    OMI_SIM_DFU_CHUNK_NET = 3,    /* continuation with image omitted (0) but a non-app area */
    OMI_SIM_DFU_STOPPED = 4,      /* upload aborted */
    OMI_SIM_DFU_PENDING = 5,      /* upload finished writing */
};

enum omi_sim_sd_state {
    OMI_SIM_SD_OK = 0,
    OMI_SIM_SD_ABSENT = 1, /* every mount fails */
    OMI_SIM_SD_SLOW = 2,   /* mounts fail until sd_ready_ms of uptime */
    OMI_SIM_SD_DEAD = 3,   /* mount succeeds, then all IO fails */
};

enum omi_sim_fault_op {
    OMI_SIM_FAULT_SETTINGS_INIT = 1, /* settings_subsys_init() returns rc */
    OMI_SIM_FAULT_SETTINGS_LOAD = 2, /* settings_load_subtree(key) returns rc */
    OMI_SIM_FAULT_SETTINGS_SAVE = 3, /* settings_save_one(key, ...) returns rc */
};

struct omi_sim_event {
    int64_t t_ms; /* local uptime of this boot */
    int32_t kind;
    int32_t value;
};

struct omi_sim_fault {
    int32_t op;
    int32_t rc;
    int32_t remaining; /* <0: every call */
    char key[40];      /* empty: any key */
};

struct omi_sim_plan {
    uint32_t reset_reason; /* raw RESETREAS for this boot (0 = power-on) */
    int32_t button_pressed;
    int32_t charging;
    int32_t battery_mv;
    int32_t connected;
    int32_t sd_state;
    int32_t sd_ready_ms;
    int32_t retained_loaded; /* 1 when retained.bin existed (warm RAM) */
    uint32_t retained_len;
    uint8_t retained[OMI_SIM_RETAINED_MAX];
    int32_t n_events;
    struct omi_sim_event events[OMI_SIM_MAX_EVENTS];
    int32_t n_faults;
    struct omi_sim_fault faults[OMI_SIM_MAX_FAULTS];
};

/* Runner side (host libc). Exit hooks call save; never called from ISRs. */
const struct omi_sim_plan *omi_sim_host_plan(void);
int omi_sim_host_save_retained(const void *data, uint32_t len);
/* Whole-file helpers for other persistent sim state (e.g. sd.img). */
int omi_sim_host_load_file(const char *name, void *data, uint32_t len);
int omi_sim_host_save_file(const char *name, const void *data, uint32_t len);
/* Write one line to stdout unsplit (the Zephyr console wraps long lines). */
void omi_sim_host_print(const char *line);

#endif
