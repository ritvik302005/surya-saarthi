"""24-hour dispatch optimizer (mixed-integer linear program, solved with HiGHS via scipy).

Each hour, plan the next PLAN_HORIZON_HOURS with the latest forecast, apply only the first
hour, and plan again next hour (model predictive control). The model follows the same
rules as the plant (nodes/safety.py) so its plans pass the safety check unchanged:
solar serves load first, the battery charges only from solar or the genset (never the
grid), the genset has a minimum load, flexible one-hour jobs run once before their
deadline and wait during power cuts, and battery efficiency, wear and BMS limits apply.

Minimises: grid import cost - export credit + battery wear + diesel + heavy penalties
for unserved essential load, missed jobs and missed operator targets - value of the
energy left in the battery at the end of the horizon.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

import config

HOUR_VARS = ["s", "sc", "x", "cur", "d", "g", "gl", "gc", "sh", "u", "y", "soc"]
# s: solar to load, sc: solar to battery, x: export, cur: curtailed solar, d: battery discharge
# to site, g: grid import, gl/gc: genset to load/battery, sh: unserved essential load,
# u: genset on (0/1), y: importing (0/1), soc: stored energy at the end of the hour (kWh)
BIG_M = 50.0
MISS_JOB_PENALTY_RS = 500.0
MISS_TARGET_PENALTY_RS_PER_KWH = 50.0


@dataclass
class Job:
    name: str
    power_kw: float
    hours: list          # horizon indices where it may run
    pending: bool        # already waiting now (decided this hour)
    miss_cost: float = MISS_JOB_PENALTY_RS   # lower for jobs that can still run after the horizon


@dataclass
class PlanInputs:
    start_hour: int
    solar_kw: list
    essential_kw: list
    price: list
    grid_available: list
    soc0_pct: float
    capacity_kwh: float
    max_charge_kw: list
    max_discharge_kw: list
    jobs: list = field(default_factory=list)
    soc_targets: list = field(default_factory=list)   # (index, min_pct)
    grid_caps: list = field(default_factory=list)     # (index, max_grid_kw) from demand response


def terminal_value_rs_per_kwh():
    """What a kWh still stored at the end of the plan is worth: delivered later at the
    normal tariff (after discharge losses), minus the wear of taking it out."""
    return max(0.0, config.BASE_TARIFF_RS_PER_KWH * config.BATTERY_DISCHARGE_EFFICIENCY - config.BATTERY_WEAR_RS_PER_KWH)


def solve(p: PlanInputs):
    H = len(p.solar_kw)
    nh = len(HOUR_VARS)
    idx = lambda k, name: k * nh + HOUR_VARS.index(name)
    job_vars = []                               # (job index, horizon hour) -> variable
    for j, job in enumerate(p.jobs):
        for k in job.hours:
            job_vars.append((j, k))
    z0 = H * nh
    miss0 = z0 + len(job_vars)
    slack0 = miss0 + len(p.jobs)
    n = slack0 + len(p.soc_targets)
    zi = {jk: z0 + i for i, jk in enumerate(job_vars)}

    eta_c, eta_d = config.BATTERY_CHARGE_EFFICIENCY, config.BATTERY_DISCHARGE_EFFICIENCY
    cap = p.capacity_kwh
    soc_min = min(config.BATTERY_RESERVE_PCT, p.soc0_pct) / 100 * cap
    soc0 = p.soc0_pct / 100 * cap
    wear = config.BATTERY_WEAR_RS_PER_KWH / eta_d          # per kWh delivered by the battery
    gmax, gmin = config.GENSET_KW, config.GENSET_KW * config.GENSET_MIN_LOAD_FRACTION

    c = np.zeros(n)
    lb, ub = np.zeros(n), np.full(n, np.inf)
    integrality = np.zeros(n)
    for k in range(H):
        c[idx(k, "g")] = p.price[k]
        c[idx(k, "x")] = -config.EXPORT_CREDIT_RS_PER_KWH
        c[idx(k, "d")] = wear
        c[idx(k, "gl")] = c[idx(k, "gc")] = config.GENSET_RS_PER_KWH
        c[idx(k, "sh")] = config.VALUE_OF_LOST_LOAD_RS_PER_KWH
        c[idx(k, "cur")] = 0.01                             # prefer storing/exporting over curtailing
        c[idx(k, "soc")] = -0.001                           # tie-break: store spare sun early, as the plant does
        ub[idx(k, "d")] = max(0.0, p.max_discharge_kw[k])
        ub[idx(k, "sh")] = max(0.0, p.essential_kw[k])
        ub[idx(k, "x")] = config.GRID_EXPORT_LIMIT_KW if p.grid_available[k] else 0.0
        ub[idx(k, "g")] = np.inf if p.grid_available[k] else 0.0
        lb[idx(k, "soc")], ub[idx(k, "soc")] = soc_min, cap
        for b in ("u", "y"):
            ub[idx(k, b)] = 1
            integrality[idx(k, b)] = 1
    for k, cap_kw in p.grid_caps:
        ub[idx(k, "g")] = min(ub[idx(k, "g")], max(0.0, cap_kw))
    for (j, k), v in zi.items():
        ub[v] = 1
        integrality[v] = 1
    ub[miss0:slack0] = 1
    c[miss0:slack0] = [job.miss_cost for job in p.jobs]
    c[slack0:n] = MISS_TARGET_PENALTY_RS_PER_KWH
    c[idx(H - 1, "soc")] -= terminal_value_rs_per_kwh()

    rows = H * 8 + len(p.jobs) + len(p.soc_targets)
    A = lil_matrix((rows, n))
    rlo, rhi = np.zeros(rows), np.zeros(rows)
    r = 0

    def row(coeffs, lo, hi):
        nonlocal r
        for var, value in coeffs:
            A[r, var] += value
        rlo[r], rhi[r] = lo, hi
        r += 1

    for k in range(H):
        v = lambda name: idx(k, name)
        # Solar is split between load, battery, export and curtailment.
        row([(v("s"), 1), (v("sc"), 1), (v("x"), 1), (v("cur"), 1)], p.solar_kw[k], p.solar_kw[k])
        # Load balance: solar + battery + grid + genset + unserved = essential + jobs running.
        coeffs = [(v("s"), 1), (v("d"), 1), (v("g"), 1), (v("gl"), 1), (v("sh"), 1)]
        coeffs += [(zi[(j, kk)], -job.power_kw) for (j, kk) in job_vars if kk == k for job in [p.jobs[j]]]
        row(coeffs, p.essential_kw[k], p.essential_kw[k])
        # Battery energy: stored(k) = stored(k-1) + charge x eta_c - discharge / eta_d.
        prev = [] if k == 0 else [(idx(k - 1, "soc"), -1)]
        rhs = soc0 if k == 0 else 0.0
        row([(v("soc"), 1), (v("sc"), -eta_c), (v("gc"), -eta_c), (v("d"), 1 / eta_d)] + prev, rhs, rhs)
        # Genset between its minimum load and its rating when on.
        row([(v("gl"), 1), (v("gc"), 1), (v("u"), -gmax)], -np.inf, 0)
        row([(v("gl"), 1), (v("gc"), 1), (v("u"), -gmin)], 0, np.inf)
        # Charging limit (BMS / rate).
        row([(v("sc"), 1), (v("gc"), 1)], -np.inf, max(0.0, p.max_charge_kw[k]))
        # Solar serves load first: no solar into the battery in an hour that imports from the grid.
        row([(v("g"), 1), (v("y"), -BIG_M)], -np.inf, 0)          # import only if y = 1
        row([(v("sc"), 1), (v("y"), BIG_M)], -np.inf, BIG_M)      # solar -> battery only if y = 0
    for j, job in enumerate(p.jobs):
        row([(zi[(j, k)], 1) for k in job.hours] + [(miss0 + j, 1)], 1, 1)
    for t, (k, min_pct) in enumerate(p.soc_targets):
        row([(idx(k, "soc"), 1), (slack0 + t, 1)], min_pct / 100 * cap, np.inf)

    result = milp(c, integrality=integrality, bounds=Bounds(lb, ub),
                  constraints=LinearConstraint(A.tocsr()[:r], rlo[:r], rhi[:r]),
                  options={"time_limit": 10})
    if result.x is None:
        raise RuntimeError(f"optimizer found no plan: {result.message}")
    x = result.x
    hourly = {name: [round(float(x[idx(k, name)]), 3) for k in range(H)] for name in HOUR_VARS}
    runs = {job.name: next((k for k in job.hours if x[zi[(j, k)]] > 0.5), None) for j, job in enumerate(p.jobs)}
    return {
        "hourly": hourly,
        "job_hour": runs,                          # horizon index each job runs at (None = missed)
        "soc_pct": [round(s / cap * 100, 1) for s in hourly["soc"]],
        "objective_rs": round(float(result.fun), 2),
    }
