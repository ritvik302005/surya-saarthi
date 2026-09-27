"""Operator notes -> checked constraints (power cuts, battery targets, demand response).

"kal shaam 7 se 10 bijli jayegi" -> power cut tomorrow 19:00-22:00.
"battery full by 6 pm"           -> battery at least 95% by 18:00.
"DISCOM: grid max 2 kW 6-8 pm"   -> demand response: import at most 2 kW, 18:00-20:00.

The LLM reads free-form Hindi / Hinglish / English into a strict schema; if it's
unavailable (or the AI budget is used up), a rule-based parser handles the common
phrasings. Either way the result is validated and shown to the operator for
confirmation before it changes anything. The LLM never controls a device.
"""
import json
import re

import config

MAX_WINDOW_HOURS = 12

OUTAGE_WORDS = r"(bijli|bijlee|light|power\s*cut|powercut|cut|outage|load\s*shedding|shutdown|बिजली|कटौती|लाइट|कट)"
TARGET_WORDS = r"(battery|बैटरी)"
DR_WORDS = r"(discom|demand\s*response|grid\s*max|limit|सीमा)"
EVENING = r"(pm|evening|shaam|sham|raat|night|शाम|रात)"
MORNING = r"(am|morning|subah|सुबह)"
AFTERNOON = r"(afternoon|dopahar|दोपहर)"
TOMORROW = r"(kal|tomorrow|कल)"


def _hour(value, text):
    """Hour of day from a number and the words around it (pm/shaam/raat/subah/dopahar)."""
    h = int(value) % 24
    if h < 12 and re.search(EVENING, text, re.I) and not (re.search(r"(raat|night|रात)", text, re.I) and h <= 4):
        return h + 12
    if h < 12 and re.search(AFTERNOON, text, re.I) and h <= 6:
        return h + 12
    return h


def _next_sim_hour(hour_of_day, now, tomorrow):
    """Absolute sim hour for an hour of day: today (or tomorrow if said, or if already past)."""
    day_start = now - now % 24
    sim = day_start + hour_of_day + (24 if tomorrow else 0)
    return sim + 24 if sim <= now and not tomorrow else sim


def _range(text):
    m = re.search(r"(\d{1,2})(?::00)?\s*(?:am|pm|baje|बजे)?\s*(?:se|से|to|till|until|-|–)\s*(\d{1,2})(?::00)?", text, re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_rules(text, now):
    """Deterministic parser for common phrasings. Returns a list of actions (possibly empty)."""
    actions = []
    tomorrow = bool(re.search(TOMORROW, text, re.I))
    has_evening = bool(re.search(EVENING, text, re.I))
    has_morning = bool(re.search(MORNING, text, re.I))
    rng = _range(text)

    if rng and re.search(DR_WORDS, text, re.I):
        cap = re.search(r"(\d+(?:\.\d+)?)\s*kw", text, re.I)
        if cap:
            start, end = _hour(rng[0], text), _hour(rng[1], text)
            s = _next_sim_hour(start, now, tomorrow)
            actions.append({"type": "dr", "start": s, "end": s + (end - start) % 24, "max_grid_kw": float(cap.group(1))})
            return actions

    if rng and re.search(OUTAGE_WORDS, text, re.I):
        a, b = rng
        if has_evening or has_morning or re.search(AFTERNOON, text, re.I):
            start, end = _hour(a, text), _hour(b, text)
            if end <= start and end < 12 and has_evening:
                end += 12 if end + 12 > start else 0
        else:
            # No am/pm said: take whichever reading starts soonest from now.
            options = [(a % 24, b % 24), ((a % 12) + 12, (b % 12) + 12)]
            start, end = min(options, key=lambda o: (_next_sim_hour(o[0], now, tomorrow) - now))
        s = _next_sim_hour(start, now, tomorrow)
        actions.append({"type": "outage", "start": s, "end": s + max(1, (end - start) % 24)})

    if re.search(TARGET_WORDS, text, re.I):
        pct = re.search(r"(\d{2,3})\s*%", text)
        full = re.search(r"(full|फुल|पूरी|charged)", text, re.I)
        by = re.search(r"(?:by|tak|तक|before)\s*(\d{1,2})|(\d{1,2})\s*(?:baje|बजे)?\s*(?:tak|तक)", text, re.I)
        if (pct or full) and by:
            hour = _hour(by.group(1) or by.group(2), text)
            actions.append({"type": "soc_target", "hour": _next_sim_hour(hour, now, tomorrow),
                            "min_pct": float(pct.group(1)) if pct else 95.0})
    return actions


NOTE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "operator_note",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "actions": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["outage", "soc_target", "dr"]},
                        "day": {"type": "string", "enum": ["today", "tomorrow"]},
                        "start_hour": {"type": "integer"},
                        "end_hour": {"type": "integer"},
                        "min_pct": {"type": "number"},
                        "max_grid_kw": {"type": "number"},
                    },
                    "required": ["type", "day", "start_hour", "end_hour", "min_pct", "max_grid_kw"],
                    "additionalProperties": False,
                }},
            },
            "required": ["actions"],
            "additionalProperties": False,
        },
    },
}

NOTE_PROMPT = """You turn a solar microgrid operator's note (Hindi, Hinglish or English) into actions.
Action types:
- "outage": a power cut expected from start_hour to end_hour (24-hour clock, end exclusive).
- "soc_target": battery at least min_pct percent by start_hour (set end_hour = start_hour).
- "dr": the grid operator asks to import at most max_grid_kw from start_hour to end_hour.
"shaam"/"evening" and "raat"/"night" mean PM hours; "subah" means AM; "kal" means tomorrow.
"Battery full" means min_pct 95. Unused fields: 0. If the note asks for nothing, return no actions.
The current hour is {now_hour}:00."""


def parse_ai(text, now):
    from langchain_core.messages import HumanMessage, SystemMessage
    from nodes.allocation import _get_llm
    response = _get_llm().invoke([SystemMessage(content=NOTE_PROMPT.format(now_hour=now % 24)),
                                  HumanMessage(content=text)], response_format=NOTE_SCHEMA)
    raw = json.loads(response.content)["actions"]
    actions = []
    for a in raw:
        tomorrow = a["day"] == "tomorrow"
        start = _next_sim_hour(int(a["start_hour"]) % 24, now, tomorrow)
        if a["type"] == "soc_target":
            actions.append({"type": "soc_target", "hour": start, "min_pct": float(a["min_pct"])})
        else:
            end = start + max(1, (int(a["end_hour"]) - int(a["start_hour"])) % 24)
            action = {"type": a["type"], "start": start, "end": end}
            if a["type"] == "dr":
                action["max_grid_kw"] = float(a["max_grid_kw"])
            actions.append(action)
    return actions


def validate(actions, now):
    """Keep only sensible actions; raise if any is out of range."""
    clean = []
    for a in actions:
        kind = a.get("type")
        if kind in ("outage", "dr"):
            start, end = int(a["start"]), int(a["end"])
            if not (now <= start < now + 48) or not (1 <= end - start <= MAX_WINDOW_HOURS):
                raise ValueError(f"{kind} window {start}-{end} is not within the next 48 hours or is longer than {MAX_WINDOW_HOURS} h")
            item = {"type": kind, "start": start, "end": end}
            if kind == "dr":
                cap = float(a["max_grid_kw"])
                if not 0 <= cap <= 20:
                    raise ValueError("demand-response limit must be 0-20 kW")
                item["max_grid_kw"] = cap
            clean.append(item)
        elif kind == "soc_target":
            hour, pct = int(a["hour"]), float(a["min_pct"])
            if not (now < hour <= now + 48) or not (config.BATTERY_RESERVE_PCT <= pct <= 100):
                raise ValueError("battery target must be within 48 hours and between the reserve and 100%")
            clean.append({"type": "soc_target", "hour": hour, "min_pct": pct})
        else:
            raise ValueError(f"unknown action type {kind!r}")
    return clean


def _when(sim_hour, now):
    day = "today" if sim_hour // 24 == now // 24 else "tomorrow" if sim_hour // 24 == now // 24 + 1 else f"day {sim_hour // 24 + 1}"
    day_hi = {"today": "आज", "tomorrow": "कल"}.get(day, day)
    return f"{day} {sim_hour % 24:02d}:00", f"{day_hi} {sim_hour % 24:02d}:00"


def describe(actions, now):
    en, hi = [], []
    for a in actions:
        if a["type"] == "outage":
            (s, s_hi), (e, e_hi) = _when(a["start"], now), _when(a["end"], now)
            en.append(f"Power cut from {s} to {e}")
            hi.append(f"बिजली कटौती {s_hi} से {e_hi} तक")
        elif a["type"] == "soc_target":
            (t, t_hi) = _when(a["hour"], now)
            en.append(f"Battery at least {a['min_pct']:.0f}% by {t}")
            hi.append(f"{t_hi} तक बैटरी कम से कम {a['min_pct']:.0f}%")
        elif a["type"] == "dr":
            (s, s_hi), (e, e_hi) = _when(a["start"], now), _when(a["end"], now)
            en.append(f"Grid import at most {a['max_grid_kw']:.1f} kW from {s} to {e}")
            hi.append(f"{s_hi} से {e_hi} तक ग्रिड से अधिकतम {a['max_grid_kw']:.1f} kW")
    return en, hi


def interpret(text, now, allow_ai=True):
    """Returns {"actions", "source", "summary_en", "summary_hi"}; raises ValueError if nothing usable."""
    text = (text or "").strip()[:300]
    if not text:
        raise ValueError("The note is empty.")
    actions, source = [], "rules"
    if allow_ai:
        try:
            actions, source = parse_ai(text, now), "ai"
        except Exception as error:
            print(f"[notes] AI parse failed ({error}); using the rule-based parser")
            actions = []
    if not actions:
        actions, source = parse_rules(text, now), "rules"
    actions = validate(actions, now)
    if not actions:
        raise ValueError("Couldn't find a power cut, battery target or grid limit in that note. "
                         "Try e.g. \"power cut 7 to 10 pm\" or \"battery full by 6 pm\".")
    en, hi = describe(actions, now)
    return {"actions": actions, "source": source, "summary_en": en, "summary_hi": hi}
