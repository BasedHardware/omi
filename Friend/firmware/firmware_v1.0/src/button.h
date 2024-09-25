#pragma once

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