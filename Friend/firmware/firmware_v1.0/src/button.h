#ifndef BUTTON_H
#define BUTTON_H

typedef enum {
    IDLE, 
    ONE_PRESS,
    TWO_PRESS,
    GRACE
} FSM_STATE_T;

int button_init();
void activate_button_work();
void register_button_service();
void turnoff_all();
FSM_STATE_T get_current_button_state();

void force_button_state(FSM_STATE_T state);

#endif