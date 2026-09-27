"""Plain-language explanations of the optimizer's decision, in English and Hindi.

Every sentence is filled in from the plan's own numbers (no LLM), so the explanation
can't claim anything the plan doesn't do.
"""


def _hh(hour):
    return f"{hour % 24:02d}:00"


def _rs(value):
    return f"Rs {value:.2f}"


def _pretty_job(name):
    return name.replace("water_pump", "Water pump").replace("ev_charging", "EV charging")


def _pretty_job_hi(name):
    return name.replace("water_pump", "पानी का पंप").replace("ev_charging", "EV चार्जिंग")


def build_facts(state, plan, decision):
    """The numbers behind this hour's decision."""
    start = state.get("sim_hour", 0)
    h = plan["hourly"]
    prices = plan["price"]
    grid_ok = plan["grid_available"]
    facts = {
        "hour": start,
        "battery_pct": state.get("battery_soc_pct", 0),
        "battery_above_reserve": state.get("battery_soc_pct", 0) > state.get("reserve_pct", 20.0) + 2,
        "grid_ok": grid_ok[0],
        "price_now": prices[0],
        "charge_kw": round(h["sc"][0] + h["gc"][0], 2),
        "discharge_kw": round(h["d"][0], 2),
        "grid_kw": round(h["g"][0], 2),
        "genset_kw": round(h["gl"][0] + h["gc"][0], 2),
        "export_kw": round(h["x"][0], 2),
        "forecast_miss_kw": state.get("forecast_miss_kw") if state.get("replanned") else None,
    }
    # Next power cut in the plan, and the battery level planned just before it.
    cut = next((k for k in range(1, len(grid_ok)) if not grid_ok[k] and grid_ok[k - 1]), None)
    if cut is not None:
        facts["next_cut_hour"] = start + cut
        facts["battery_at_cut_pct"] = plan["soc_pct"][cut - 1]
    # When the battery is next used, and what the grid costs then.
    use = next((k for k in range(1, len(h["d"])) if h["d"][k] > 0.1), None)
    if use is not None and grid_ok[use]:   # battery used during a cut is covered by the power-cut reason
        facts["next_use_hour"] = start + use
        facts["price_at_use"] = prices[use]
    # Jobs waiting now: when the plan runs them, and at what price.
    moved = []
    for name in decision.get("defer_loads", []):
        k = plan["job_hour"].get(name)
        if k is not None and k > 0:
            moved.append({"name": name, "hour": start + k, "price": prices[k]})
    facts["moved_jobs"] = moved
    return facts


def explain(facts):
    """(English, Hindi) sentences: what happens this hour, then up to two reasons."""
    f = facts
    en, hi = [], []

    if not f["grid_ok"]:
        src = " and genset" if f["genset_kw"] > 0.05 else ""
        src_hi = " और जनरेटर" if f["genset_kw"] > 0.05 else ""
        en.append(f"Power cut: essential load runs on solar, battery{src}; other jobs wait.")
        hi.append(f"बिजली कटौती: ज़रूरी लोड सोलर, बैटरी{src_hi} से चल रहा है; बाकी काम रुके हैं।")
    elif f["charge_kw"] > 0.05:
        en.append(f"Storing {f['charge_kw']:.1f} kW of spare sunshine in the battery.")
        hi.append(f"धूप की {f['charge_kw']:.1f} kW अतिरिक्त बिजली बैटरी में जमा हो रही है।")
    elif f["discharge_kw"] > 0.05:
        en.append(f"Battery is supplying {f['discharge_kw']:.1f} kW while grid power costs {_rs(f['price_now'])}/kWh.")
        hi.append(f"बैटरी {f['discharge_kw']:.1f} kW दे रही है, अभी ग्रिड {_rs(f['price_now'])}/kWh पर है।")
    elif f["grid_kw"] > 0.05:
        en.append(f"Buying {f['grid_kw']:.1f} kW from the grid at {_rs(f['price_now'])}/kWh.")
        hi.append(f"ग्रिड से {f['grid_kw']:.1f} kW ली जा रही है, {_rs(f['price_now'])}/kWh पर।")
    else:
        en.append("Sunshine covers the load this hour.")
        hi.append("इस घंटे धूप से पूरा लोड चल रहा है।")

    reasons_en, reasons_hi = [], []
    if f.get("next_cut_hour") is not None and f["grid_ok"]:
        reasons_en.append(f"planning to have the battery at about {f['battery_at_cut_pct']:.0f}% when the power cut starts at {_hh(f['next_cut_hour'])}")
        reasons_hi.append(f"{_hh(f['next_cut_hour'])} की बिजली कटौती शुरू होने तक बैटरी लगभग {f['battery_at_cut_pct']:.0f}% रखने की योजना है")
    if not f["battery_above_reserve"] and f["grid_ok"] and f["discharge_kw"] <= 0.05 and f["charge_kw"] <= 0.05:
        reasons_en.append("the battery is at its safety reserve, so it can't supply more now")
        reasons_hi.append("बैटरी अपने सुरक्षित न्यूनतम स्तर पर है, इसलिए अभी और नहीं दे सकती")
    elif (f.get("next_use_hour") is not None and f["grid_ok"] and f["discharge_kw"] <= 0.05
          and f["battery_above_reserve"] and f["price_at_use"] > f["price_now"]):
        reasons_en.append(f"saving battery for {_hh(f['next_use_hour'])}, when grid power costs {_rs(f['price_at_use'])} instead of {_rs(f['price_now'])}")
        reasons_hi.append(f"बैटरी {_hh(f['next_use_hour'])} के लिए बचाई जा रही है, तब ग्रिड {_rs(f['price_at_use'])} होगा (अभी {_rs(f['price_now'])})")
    for job in f["moved_jobs"][:1]:
        reasons_en.append(f"{_pretty_job(job['name'])} moved to {_hh(job['hour'])} ({_rs(job['price'])}/kWh), still before its deadline")
        reasons_hi.append(f"{_pretty_job_hi(job['name'])} {_hh(job['hour'])} पर होगी ({_rs(job['price'])}/kWh), समय-सीमा से पहले")
    if f.get("forecast_miss_kw") is not None:
        word, word_hi = ("below", "कम") if f["forecast_miss_kw"] < 0 else ("above", "ज़्यादा")
        reasons_en.append(f"sunlight is {abs(f['forecast_miss_kw']):.1f} kW {word} forecast, so the plan was updated")
        reasons_hi.append(f"धूप अनुमान से {abs(f['forecast_miss_kw']):.1f} kW {word_hi} है, इसलिए योजना बदली गई")

    if reasons_en:
        en.append(("Why: " + "; ".join(reasons_en[:2]) + "."))
        hi.append(("क्यों: " + "; ".join(reasons_hi[:2]) + "।"))
    return " ".join(en), " ".join(hi)
