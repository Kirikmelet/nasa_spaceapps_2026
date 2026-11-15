def chart_geometry(rows, w=800, h=240, pad=24):
    if not rows:
        return {"line": "", "points": [], "w": w, "h": h}
    vals = [r["value"] for r in rows]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = max(len(rows) - 1, 1)
    pts = [{
        "x": round(pad + i * (w - 2 * pad) / n, 1),
        "y": round(h - pad - (r["value"] - lo) / span * (h - 2 * pad), 1),
        "status": r["status"], "time": r["time"], "value": r["value"],
    } for i, r in enumerate(rows)]
    return {"line": " ".join(f"{p['x']},{p['y']}" for p in pts),
            "points": pts, "w": w, "h": h}
