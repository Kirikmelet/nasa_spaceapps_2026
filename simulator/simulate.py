"""Astronaut vitals simulator.

Posts one reading per astronaut every --interval seconds to POST /api/dummy/vitals.
Talks to the server only through the HTTP API.

Usage (server must be running: python -m uvicorn app.main:app --reload):
    python simulator/simulate.py
    python simulator/simulate.py --url http://localhost:8000 --interval 2

Fault injection while it runs (type a command + Enter in this terminal):
    hr [astro_id]     resting HR drifts to ~95 (no hard limit; baseline detector flags it)
    hrhigh [astro_id] HR ~140 (critical at rest, normal during exercise)
    spo2 [astro_id]   SpO2 drops to ~85 (hard-limit critical)
    temp [astro_id]   low fever, ~38.2 C (hard-limit warning)
    fever [astro_id]  high fever, ~39.5 C (hard-limit critical)
    bp [astro_id]     high blood pressure, ~150/95 (hard-limit warning)
    resp [astro_id]   fast breathing, ~24/min (hard-limit warning)
    clear [astro_id]  back to normal (omit id to clear all)
Unresolved warnings escalate to critical after 5 minutes (good demo).

Activity (changes the astronaut's normal vitals and the reading's activity):
    rest [astro_id]
    sleep [astro_id]
    exercise [astro_id]

Context-aware demo: `exercise astro_2` (HR ~130-140, no alert), then
`hrhigh astro_1` (same HR at rest -> critical).

    quit

Or script it: --hr-fault-at 60 --spo2-fault-at 120 (seconds after start).

NOTE: the engine's non-HR limits are not activity-aware yet, so the activity
offsets below keep temp, resp and BP inside the rest limits.
Allow ~40-60 s of warm-up so each baseline has 20+ samples before faults.
Baselines are per activity, so baseline alerts pause ~40 s after a switch
(hard limits still work immediately).
"""
import argparse
import random
import sys
import threading
import time
from datetime import datetime

import requests

# Per-astronaut resting baselines: (mean, std). All inside the engine's rest limits.
PROFILES = {
    "astro_1": {"hr": (70, 2.0), "spo2": (98, 0.5), "temp": (36.8, 0.10),
                "bp_sys": (118, 3.0), "bp_dia": (76, 2.0), "resp": (14, 0.8)},
    "astro_2": {"hr": (62, 2.0), "spo2": (97.5, 0.5), "temp": (36.6, 0.10),
                "bp_sys": (112, 3.0), "bp_dia": (72, 2.0), "resp": (13, 0.8)},
    "astro_3": {"hr": (78, 2.5), "spo2": (98.5, 0.4), "temp": (36.9, 0.10),
                "bp_sys": (124, 3.0), "bp_dia": (80, 2.0), "resp": (15, 0.8)},
}

# Activity -> {metric: offset added to the astronaut's own resting mean}.
# Offsets (not fixed values) keep each astronaut's baseline personal.
# Exercise stays under the fixed non-HR limits: resp < 20, bp_sys < 140,
# bp_dia < 90, temp < 37.8. Sleep stays above resp 10 and HR 45.
ACTIVITY_OFFSETS = {
    "rest":     {},
    "sleep":    {"hr": -8, "resp": -1, "bp_sys": -6, "bp_dia": -4, "temp": -0.2},
    "exercise": {"hr": 70, "resp": 3, "bp_sys": 6, "bp_dia": 4, "temp": 0.3},
}

# Fault name -> {metric: target mean}. Noise uses the astronaut's normal std.
FAULTS = {
    "hr":     {"hr": 95},                     # below rest warn_high (100): only the baseline detector catches it
    "hrhigh": {"hr": 140},                    # above rest critical_high (130), below exercise warn_high (170)
    "spo2":   {"spo2": 85},                   # below critical_low (90)
    "temp":   {"temp": 38.2},                 # above warn_high (37.8), below critical (39.0)
    "fever":  {"temp": 39.5},                 # above critical_high (39.0)
    "bp":     {"bp_sys": 150, "bp_dia": 95},  # above warn_high (140/90), below critical (180/120)
    "resp":   {"resp": 24},                   # above warn_high (20), below critical (30)
}

faults = {}            # astronaut_id -> fault name
activities = {}        # astronaut_id -> "rest" | "sleep" | "exercise" (default rest)
state_lock = threading.Lock()


def make_reading(astro_id):
    p = PROFILES[astro_id]
    with state_lock:
        fault = faults.get(astro_id)
        activity = activities.get(astro_id, "rest")
    offsets = ACTIVITY_OFFSETS[activity]
    vals = {m: random.gauss(mean + offsets.get(m, 0), std) for m, (mean, std) in p.items()}
    if fault in FAULTS:
        for metric, target in FAULTS[fault].items():
            vals[metric] = random.gauss(target, p[metric][1])
    return {
        "astronaut_id": astro_id,
        "timestamp": datetime.now().isoformat(),  # escalation uses these timestamps
        "hr": round(vals["hr"]),
        "spo2": round(min(vals["spo2"], 100), 1),
        "temp": round(vals["temp"], 1),
        "bp_sys": round(vals["bp_sys"]),
        "bp_dia": round(vals["bp_dia"]),
        "resp": round(vals["resp"]),
        "activity": activity,
    }


def set_fault(kind, astro_id=None):
    targets = [astro_id] if astro_id else ["astro_1"]
    with state_lock:
        for a in targets:
            if a not in PROFILES:
                print(f"  unknown astronaut '{a}' (have: {', '.join(PROFILES)})")
                continue
            if kind == "clear":
                faults.pop(a, None)
            else:
                faults[a] = kind
            print(f"  {a}: {kind}")


def set_activity(activity, astro_id=None):
    target = astro_id or "astro_1"
    if target not in PROFILES:
        print(f"  unknown astronaut '{target}' (have: {', '.join(PROFILES)})")
        return
    with state_lock:
        activities[target] = activity
    print(f"  {target}: activity -> {activity}")


def clear_all():
    with state_lock:
        faults.clear()
    print("  all faults cleared")


HELP = ("  faults: hr | hrhigh | spo2 | temp | fever | bp | resp  [id]  |  clear [id]\n"
        "  activity: rest | sleep | exercise  [id]  |  quit")


def command_loop():
    while True:
        try:
            line = input().strip().lower()
        except EOFError:
            return
        if not line:
            continue
        parts = line.split()
        cmd, arg = parts[0], (parts[1] if len(parts) > 1 else None)
        if cmd in FAULTS:
            set_fault(cmd, arg)
        elif cmd in ACTIVITY_OFFSETS:
            set_activity(cmd, arg)
        elif cmd == "clear":
            set_fault("clear", arg) if arg else clear_all()
        elif cmd in ("quit", "exit", "q"):
            print("bye")
            import os
            os._exit(0)
        else:
            print(HELP)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--hr-fault-at", type=float, help="seconds after start: inject HR drift on astro_1")
    ap.add_argument("--spo2-fault-at", type=float, help="seconds after start: inject SpO2 drop on astro_2")
    args = ap.parse_args()

    endpoint = args.url.rstrip("/") + "/api/dummy/vitals"
    start = time.time()
    scheduled = []
    if args.hr_fault_at is not None:
        scheduled.append([args.hr_fault_at, "hr", "astro_1"])
    if args.spo2_fault_at is not None:
        scheduled.append([args.spo2_fault_at, "spo2", "astro_2"])

    threading.Thread(target=command_loop, daemon=True).start()
    print(f"Posting to {endpoint} every {args.interval}s for {', '.join(PROFILES)}.")
    print(HELP + "\n  (warm up ~60 s first)")

    session = requests.Session()
    n = 0
    while True:
        elapsed = time.time() - start
        for item in scheduled[:]:
            if elapsed >= item[0]:
                print(f"[{elapsed:5.0f}s] scheduled fault:")
                set_fault(item[1], item[2])
                scheduled.remove(item)

        for astro_id in PROFILES:
            try:
                r = session.post(endpoint, json=make_reading(astro_id), timeout=5)
                if r.status_code != 200:
                    print(f"  {astro_id}: HTTP {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                print(f"  server not reachable ({e.__class__.__name__}); retrying...")
                break
        n += 1
        if n % 10 == 0:
            print(f"[{elapsed:5.0f}s] {n} rounds sent")
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
