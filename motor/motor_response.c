/**
 * Motor Response Controller - Ola S1 Pro
 * Module: Motor Firmware
 * Version: 2.1.0
 */

#define MOTOR_CUTOFF_ON_BRAKE    1
#define REGEN_BRAKING_STRENGTH   0.4
#define MAX_REGEN_SPEED_KMPH     80

typedef struct {
    float speed_kmph;
    float motor_torque_nm;
    float regen_current_amps;
    int   brake_signal_received;
} MotorState;

/**
 * When brake is applied, motor must cut power
 * and switch to regenerative braking mode
 * CRITICAL - must sync with abs_controller.c
 */
void on_brake_signal(MotorState *state) {
    if (state->brake_signal_received && MOTOR_CUTOFF_ON_BRAKE) {
        state->motor_torque_nm = 0;

        // Enable regenerative braking only below safe speed
        if (state->speed_kmph < MAX_REGEN_SPEED_KMPH) {
            state->regen_current_amps = REGEN_BRAKING_STRENGTH * state->speed_kmph;
        }
    }
}

/**
 * Main motor update loop called every 10ms
 */
void update_motor(MotorState *state, float throttle_input) {
    if (!state->brake_signal_received) {
        state->motor_torque_nm = throttle_input * 58.0;
    } else {
        on_brake_signal(state);
    }
}