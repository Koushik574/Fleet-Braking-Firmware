/**
 * ECU Master Controller - Ola S1 Pro
 * Central controller that coordinates all modules
 * Version: 2.1.0
 */

#include "braking/abs_controller.c"
#include "motor/motor_response.c"
#include "battery/battery_manager.c"

#define ECU_LOOP_INTERVAL_MS  10

typedef struct {
    BrakeState   brake;
    MotorState   motor;
    BatteryState battery;
} VehicleState;

/**
 * Main ECU loop - runs every 10ms
 * Coordinates braking + motor + battery together
 */
void ecu_main_loop(VehicleState *vehicle, float pedal_input, float throttle_input) {

    // Step 1 - Apply brakes if pedal pressed
    if (pedal_input > 0) {
        apply_brakes(&vehicle->brake, pedal_input);
        vehicle->motor.brake_signal_received = 1;
    } else {
        vehicle->motor.brake_signal_received = 0;
    }

    // Step 2 - Update motor based on brake signal
    update_motor(&vehicle->motor, throttle_input);

    // Step 3 - Send regen current to battery
    accept_regen_current(&vehicle->battery, vehicle->motor.regen_current_amps);

    // Step 4 - Monitor battery health
    monitor_battery(&vehicle->battery);
}