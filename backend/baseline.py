"""Rule-based controller used as the comparison baseline.

It sees exactly the same solar and demand as the agent each cycle, but works
the way a typical fixed-rule controller does: solar first, then battery down
to the reserve, then grid. Surplus solar charges the battery and the rest is
exported (net metering, same as the agent). It never defers a load and ignores
the price.
"""
from config import (CYCLE_HOURS, BATTERY_RESERVE_PCT, BATTERY_MAX_CHARGE_KW, BATTERY_MAX_DISCHARGE_KW,
                    GRID_EXPORT_LIMIT_KW, EXPORT_CREDIT_RS_PER_KWH)


def rule_based_step(soc_pct, capacity_kwh, solar_kw, critical_kw, new_flexible_loads, price):
    demand_kw = critical_kw + sum(load["power_kw"] for load in new_flexible_loads)

    solar_used = min(solar_kw, demand_kw)
    remaining = demand_kw - solar_used

    available_kwh = max(0, (soc_pct - BATTERY_RESERVE_PCT) / 100 * capacity_kwh)
    battery_kw = min(remaining, available_kwh / CYCLE_HOURS, BATTERY_MAX_DISCHARGE_KW)
    grid_kw = remaining - battery_kw

    surplus = solar_kw - solar_used
    export_kw = 0.0
    if surplus > 0:
        room_kwh = max(0, (100 - soc_pct) / 100 * capacity_kwh)
        battery_kw = -min(surplus, room_kwh / CYCLE_HOURS, BATTERY_MAX_CHARGE_KW)
        export_kw = min(surplus + battery_kw, GRID_EXPORT_LIMIT_KW)   # same net metering as the agent

    new_soc = min(100, max(0, soc_pct - battery_kw * CYCLE_HOURS / capacity_kwh * 100))
    return {
        "grid_kw": round(grid_kw, 2),
        "battery_kw": round(battery_kw, 2),
        "demand_kw": round(demand_kw, 2),
        "cost_rs": round(grid_kw * price * CYCLE_HOURS, 2),
        "export_kw": round(export_kw, 2),
        "net_cost_rs": round((grid_kw * price - export_kw * EXPORT_CREDIT_RS_PER_KWH) * CYCLE_HOURS, 2),
        "solar_self_used_kw": round(solar_used + max(0, -battery_kw), 2),
        "soc_pct": round(new_soc, 2),
    }
