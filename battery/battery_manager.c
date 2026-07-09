/**
 * Battery Manager - Ola S1 Pro
 * Module: Battery Firmware
 * Version: 2.1.0
 */

#define MAX_CHARGE_CURRENT_AMPS     12.0
#define OVERHEAT_TEMP_CELSIUS       55.0
#define LOW_BATTERY_THRESHOLD_PCT   10.0
#define REGEN_MAX_CHARGE_AMPS       8.0

typedef struct {
    float battery_pct;
    float temperature_celsius;
    float charge_current_amps;
    int   overheat_protection_active;
} BatteryState;

/**
 * Accepts regenerative braking current from motor
 * Must not exceed REGEN_MAX_CHARGE_AMPS
 */
void accept_regen_current(BatteryState *state, float regen_amps) {
    if (state->temperature_celsius > OVERHEAT_TEMP_CELSIUS) {
        state->overheat_protection_active = 1;
        state->charge_current_amps        = 0;
        return;
    }

    // Cap regen current for battery safety
    if (regen_amps > REGEN_MAX_CHARGE_AMPS) {
        regen_amps = REGEN_MAX_CHARGE_AMPS;
    }

    state->charge_current_amps = regen_amps;
}

/**
 * Main battery monitoring loop
 */
void monitor_battery(BatteryState *state) {
    if (state->temperature_celsius > OVERHEAT_TEMP_CELSIUS) {
        state->overheat_protection_active = 1;
        state->charge_current_amps        = 0;
    }

    if (state->battery_pct < LOW_BATTERY_THRESHOLD_PCT) {
        // Reduce regen current at low battery
        state->charge_current_amps = state->charge_current_amps * 0.5;
    }
}