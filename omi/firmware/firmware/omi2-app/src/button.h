/**
 * @file button.h
 * @brief Button interface for user interaction
 * 
 * This module manages the physical button on the device, providing functionality
 * for detecting button presses, handling different press patterns (single tap,
 * double tap, long press), and reporting button events to the rest of the system
 * and connected Bluetooth devices.
 */
#ifndef BUTTON_H
#define BUTTON_H

/**
 * @brief Button state machine states
 * 
 * Defines the possible states of the button state machine:
 * - IDLE: Normal state, waiting for user input
 * - GRACE: Transitional state after a button event
 */
typedef enum {
    IDLE, 
    GRACE
} FSM_STATE_T;

/**
 * @brief Initialize the button interface
 * 
 * Sets up GPIO pins, interrupt handlers, and other hardware
 * required for button functionality.
 *
 * @return 0 if successful, negative errno code if error
 */
int button_init();

/**
 * @brief Activate the button processing work queue
 * 
 * Starts the periodic button scanning and debouncing task
 * that detects button events and handles state transitions.
 */
void activate_button_work();

/**
 * @brief Register the button Bluetooth service
 * 
 * Makes the button service available over Bluetooth, allowing
 * connected devices to receive button event notifications.
 */
void register_button_service();

/**
 * @brief Power off all device subsystems
 * 
 * Called when the power button is long-pressed to shutdown
 * all device peripherals and enter a low-power state.
 */
void turnoff_all();

/**
 * @brief Get the current button state machine state
 * 
 * Returns the current state of the button state machine.
 *
 * @return Current button state (IDLE or GRACE)
 */
FSM_STATE_T get_current_button_state();

/**
 * @brief Force the button state machine to a specific state
 * 
 * Manually sets the button state machine to a given state,
 * used for testing or for recovery from error conditions.
 *
 * @param state The state to force the button state machine into
 */
void force_button_state(FSM_STATE_T state);

#endif
