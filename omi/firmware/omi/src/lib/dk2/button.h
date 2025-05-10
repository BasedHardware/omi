#ifndef BUTTON_H
#define BUTTON_H

#include <zephyr/kernel.h>
#include <zephyr/input/input.h>

typedef enum {
    IDLE, 
    GRACE
} FSM_STATE_T;

int button_init();
void activate_button_work();
void register_button_service();
void turnoff_all();
FSM_STATE_T get_current_button_state();

void force_button_state(FSM_STATE_T state);

// Input message queue from evt/button.c
extern struct k_msgq input_button;

#endif
