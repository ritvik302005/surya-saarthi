"""Software battery management system (pack level).

A real BMS publishes live charge/discharge limits that the inverter and energy
manager must respect. This one derives them from the battery level, its estimated
temperature and its state of health, and raises alarms. Faults can be injected
(e.g. "overtemp") to test that the rest of the system backs off safely.
Cell-level modelling and Kalman-filter state estimation are not included.
"""
import config

FAULTS = {
    "overtemp": "Battery over-temperature (injected fault)",
    "sensor_lost": "Battery sensor signal lost (injected fault)",
}


def bms_limits(soc_pct, soh, air_temp_c=None, fault=None):
    air = config.DEFAULT_AIR_TEMP_C if air_temp_c is None else air_temp_c
    temp = air + config.BMS_BATTERY_TEMP_RISE_C
    alarms = []
    charge = config.BATTERY_MAX_CHARGE_KW
    discharge = config.BATTERY_MAX_DISCHARGE_KW

    # Charging tapers near full; discharge tapers near the reserve.
    if soc_pct > config.BMS_CHARGE_TAPER_START_PCT:
        span = 100.0 - config.BMS_CHARGE_TAPER_START_PCT
        charge *= max(0.0, (100.0 - soc_pct) / span)
    if soc_pct < config.BMS_DISCHARGE_TAPER_END_PCT:
        span = config.BMS_DISCHARGE_TAPER_END_PCT - config.BATTERY_RESERVE_PCT
        discharge *= max(0.0, (soc_pct - config.BATTERY_RESERVE_PCT) / span)

    if fault == "overtemp":
        temp = max(temp, config.BMS_CUTOFF_TEMP_C + 1.0)
    if fault == "sensor_lost":
        charge = discharge = 0.0
        alarms.append("Battery sensor lost: battery isolated until the signal returns.")
    elif temp >= config.BMS_CUTOFF_TEMP_C:
        charge = discharge = 0.0
        alarms.append(f"Battery at about {temp:.0f} degC: disconnected to protect it.")
    elif temp >= config.BMS_DERATE_TEMP_C:
        charge *= 0.5
        discharge *= 0.5
        alarms.append(f"Battery at about {temp:.0f} degC: charge and discharge limits halved.")
    if temp < config.BMS_MIN_CHARGE_TEMP_C:
        charge = 0.0
        alarms.append("Battery below 0 degC: charging blocked (LFP cells).")
    if soh < config.BATTERY_END_OF_LIFE_SOH:
        alarms.append(f"Battery health {soh * 100:.0f}%: at end of life, plan a replacement.")

    return {
        "max_charge_kw": round(charge, 2),
        "max_discharge_kw": round(discharge, 2),
        "battery_temp_c": round(temp, 1),
        "soh_pct": round(soh * 100, 2),
        "capacity_kwh": round(config.BATTERY_CAPACITY_KWH * soh, 3),
        "alarms": alarms,
        "fault": fault,
    }
