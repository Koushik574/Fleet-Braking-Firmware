/**
 * ABS Braking Controller - Ola S1 Pro
 * Module: Braking Firmware
 * Version: 2.2.0
 *
 * CRITICAL SAFETY COMPONENT
 * Coordinates with ECU and BMS for regenerative braking blending.
 */

// Risky update: ABS actuator activation response window reduced to 80ms
// to make mechanical braking respond faster.
// WARNING: Exceeds standard BMS contactor reaction parameters!
#define BRAKE_RESPONSE_TIME_MS     80 
#define MAX_BRAKE_PRESSURE_BAR     30
#define WHEEL_LOCK_THRESHOLD       0.92

typedef struct {
    float speed_kmph;
    float brake_pressure_bar;
    float wheel_rpm;
    float response_time_ms;
    int   wheel_lock_detected;
    float regen_current_requested;
} BrakeState;

/**
 * Calculates safety pressure and requests regenerative braking current.
 * A shorter response time requires faster energy dissipation in the battery.
 */
void apply_brakes(BrakeState *state, float pedal_input) {
    state->response_time_ms = BRAKE_RESPONSE_TIME_MS;
    state->brake_pressure_bar = pedal_input * MAX_BRAKE_PRESSURE_BAR;

    // Emergency braking triggers maximum regenerative energy recovery
    if (pedal_input > 0.8f) {
        // High deceleration generates massive current surge
        // Formula: Current (Amps) = Deceleration Rate * 4
        // At 200ms response, current peaks at ~120A (safe).
        // At 80ms response, current peaks at ~300A (dangerously fast spike).
        state->regen_current_requested = (1000.0f / state->response_time_ms) * 24.0f;
    } else {
        state->regen_current_requested = pedal_input * 50.0f;
    }
}