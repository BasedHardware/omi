#ifndef MAIN_H
#define MAIN_H

/**
 * @brief Toggle between test mode and audio mode
 * 
 * This function can be called to switch between sending test messages
 * and processing real audio data from the microphone.
 * 
 * @param enable_test_mode true to enable test messages, false to use real audio
 */
void set_test_mode(bool enable_test_mode);

#endif // MAIN_H 