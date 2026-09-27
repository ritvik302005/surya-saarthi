"""Physical models shared by every controller (AI, optimizer, fixed rule).

Solar: PVWatts-style losses, cell-temperature derating and inverter clipping.
Battery: charge/discharge efficiency, wear cost and state of health.
Genset: fuel cost and CO2. All parameters live in config.py.
"""
import config


def cell_temp_c(ghi_w_m2, air_temp_c):
    """NOCT cell-temperature model: the panel runs hotter than the air in sunshine."""
    return air_temp_c + (config.PV_NOCT_C - 20.0) / 800.0 * max(0.0, ghi_w_m2)


def pv_ac_kw(ghi_w_m2, air_temp_c=None, capacity_kw=None):
    """AC solar output for one hour of irradiance (W/m2) and air temperature (degC)."""
    if air_temp_c is None:
        air_temp_c = config.DEFAULT_AIR_TEMP_C
    if capacity_kw is None:
        capacity_kw = config.SYSTEM_CAPACITY_KW
    ghi = max(0.0, ghi_w_m2)
    temp_factor = 1.0 + config.PV_TEMP_COEFF_PER_C * (cell_temp_c(ghi, air_temp_c) - 25.0)
    dc_kw = capacity_kw * ghi / 1000.0 * (1.0 - config.PV_SYSTEM_LOSSES) * max(0.0, temp_factor)
    return round(min(dc_kw * config.INVERTER_EFFICIENCY, config.INVERTER_AC_KW), 2)


def soc_after(soc_pct, battery_kw, capacity_kwh, hours=None):
    """Battery level after one step. battery_kw > 0 is discharge delivered to the site
    (the battery loses more than that); < 0 is charging power drawn from solar/genset
    (the battery stores less than that)."""
    hours = config.CYCLE_HOURS if hours is None else hours
    if battery_kw >= 0:
        stored_change_kwh = -battery_kw * hours / config.BATTERY_DISCHARGE_EFFICIENCY
    else:
        stored_change_kwh = -battery_kw * hours * config.BATTERY_CHARGE_EFFICIENCY
    return min(100.0, max(0.0, soc_pct + stored_change_kwh / capacity_kwh * 100.0))


def max_discharge_kw(soc_pct, capacity_kwh, reserve_pct=None, hours=None):
    """Most power the battery can deliver this step without going below the reserve."""
    reserve_pct = config.BATTERY_RESERVE_PCT if reserve_pct is None else reserve_pct
    hours = config.CYCLE_HOURS if hours is None else hours
    stored_above_reserve = max(0.0, (soc_pct - reserve_pct) / 100.0 * capacity_kwh)
    return stored_above_reserve * config.BATTERY_DISCHARGE_EFFICIENCY / hours


def max_charge_kw(soc_pct, capacity_kwh, hours=None):
    """Most charging power the battery can take this step without passing 100%."""
    hours = config.CYCLE_HOURS if hours is None else hours
    room = max(0.0, (100.0 - soc_pct) / 100.0 * capacity_kwh)
    return room / config.BATTERY_CHARGE_EFFICIENCY / hours


def wear_cost_rs(battery_kw, hours=None):
    """Wear cost of energy taken out of the battery this step."""
    hours = config.CYCLE_HOURS if hours is None else hours
    return max(0.0, battery_kw) * hours / config.BATTERY_DISCHARGE_EFFICIENCY * config.BATTERY_WEAR_RS_PER_KWH


def soh_after(soh, battery_kw, hours=None):
    """State of health after one step: capacity fades in proportion to energy taken out,
    reaching BATTERY_END_OF_LIFE_SOH after the rated lifetime throughput. (Calendar ageing
    and temperature effects are not modelled.)"""
    hours = config.CYCLE_HOURS if hours is None else hours
    discharged_kwh = max(0.0, battery_kw) * hours / config.BATTERY_DISCHARGE_EFFICIENCY
    lifetime_kwh = config.BATTERY_CYCLE_LIFE * config.BATTERY_CYCLE_DEPTH * config.BATTERY_CAPACITY_KWH
    return max(0.0, soh - (1.0 - config.BATTERY_END_OF_LIFE_SOH) * discharged_kwh / lifetime_kwh)


def genset_fuel_l(genset_kw, hours=None):
    hours = config.CYCLE_HOURS if hours is None else hours
    return max(0.0, genset_kw) * hours / config.GENSET_KWH_PER_L
