#ifndef BUTTON_H
#define BUTTON_H

// Button states
#define DEFAULT_STATE 0
#define SINGLE_TAP 1    // Quick press and release
#define DOUBLE_TAP 2    // Two quick presses - Currently used for voice interaction
#define LONG_TAP 3      // Long press - Currently used for sleep/wake
#define BUTTON_PRESS 4  // Button down event
#define BUTTON_RELEASE 5 // Button up event

typedef enum {
    IDLE,
    ONE_PRESS,
    TWO_PRESS,
    GRACE
} FSM_STATE_T;

int button_init();
void activate_button_work();
void register_button_service();
FSM_STATE_T get_current_button_state();

#endif
