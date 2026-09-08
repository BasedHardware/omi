#ifndef OMI_BUTTON_INPUT_H
#define OMI_BUTTON_INPUT_H

#include <stdbool.h>

enum button_input_event { BUTTON_INPUT_SINGLE, BUTTON_INPUT_DOUBLE, BUTTON_INPUT_LONG, BUTTON_INPUT_RELEASE };

/* Events are delivered in workqueue context; edge capture is safe in the GPIO ISR. */
void button_input_start(void (*notify)(enum button_input_event), int (*read_level)(void));
void button_input_edge(bool pressed);

#endif
