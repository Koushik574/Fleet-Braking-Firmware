/**
 * ABS Braking Controller - Ola S1 Pro
 * Module: Braking Firmware
 * Version: 2.1.0
 */

#define BRAKE_RESPONSE_TIME_MS     200
#define MAX_BRAKE_PRESSURE_BAR     45
#define WHEEL_LOCK_THRESHOLD       0.85
#define SAFE_SPEED_THRESHOLD_KMPH  15

typedef struct {
    float speed_kmph;
    float brake_pressure_bar;
    float wheel_rpm;
    float response_time_ms;
    int   wheel_lock_detected;
} BrakeState;

/**
 * Checks if wheel is locked and releases pressure
 * CRITICAL SAFETY FUNCTION - DO NOT MODIFY WITHOUT TESTING
 */
void handle_wheel_lock(BrakeState *state) {
    if (state->wheel_rpm < WHEEL_LOCK_THRESHOLD) {
        state->wheel_lock_detected = 1;
        state->brake_pressure_bar  = state->brake_pressure_bar * 0.6;
    }
}

/**
 * Main braking function called every 10ms
 */
void apply_brakes(BrakeState *state, float pedal_input) {
    state->response_time_ms  = BRAKE_RESPONSE_TIME_MS;
    state->brake_pressure_bar = pedal_input * MAX_BRAKE_PRESSURE_BAR;

    // Safety check - handle wheel lock
    handle_wheel_lock(state);

    // Do not apply full brakes at very low speed
    if (state->speed_kmph < SAFE_SPEED_THRESHOLD_KMPH) {
        state->brake_pressure_bar = state->brake_pressure_bar * 0.4;
    }
}