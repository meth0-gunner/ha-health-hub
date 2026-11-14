"""Body measures entered by hand: waist, blood pressure and blood tests.

Weight is separate (the Body page's weigh-ins); BMI is worked out from the
latest weigh-in and the height in Settings. Pure Python: no Home Assistant
imports.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

from .store import Store


class BodyError(ValueError):
    pass


# key: (label, unit, lowest, highest, decimals, group)
MEASURES: dict[str, tuple[str, str, float, float, int, str]] = {
    "waist_cm": ("Waist", "cm", 40, 200, 1, "body"),
    "bp": ("Blood pressure", "mmHg", 0, 0, 0, "body"),  # two numbers, see BP_RANGES
    "hba1c": ("HbA1c", "%", 3, 20, 1, "blood"),
    "glucose_fasting": ("Fasting glucose", "mmol/L", 2, 30, 1, "blood"),
    "ldl": ("LDL cholesterol", "mmol/L", 0.2, 15, 1, "blood"),
    "hdl": ("HDL cholesterol", "mmol/L", 0.2, 5, 2, "blood"),
    "triglycerides": ("Triglycerides", "mmol/L", 0.2, 30, 1, "blood"),
}
BP_RANGES = {"bp_sys": (70, 260), "bp_dia": (40, 160)}


def stored_metrics(key: str) -> tuple[str, ...]:
    return ("bp_sys", "bp_dia") if key == "bp" else (key,)


def log(store: Store, key: str, ts: int, value: float, value2: float | None = None) -> None:
    if key not in MEASURES:
        raise BodyError(f"unknown measure {key}")
    if key == "bp":
        if value2 is None:
            raise BodyError("blood pressure needs both numbers, like 122 over 78")
        sys_, dia = float(value), float(value2)
        for name, v in (("bp_sys", sys_), ("bp_dia", dia)):
            lo, hi = BP_RANGES[name]
            if not lo <= v <= hi:
                raise BodyError(f"{'top' if name == 'bp_sys' else 'bottom'} number should be between {lo} and {hi}")
        if dia >= sys_:
            raise BodyError("the top number (systolic) should be higher than the bottom one")
        store.add_measurement(ts, "bp_sys", round(sys_), "manual")
        store.add_measurement(ts, "bp_dia", round(dia), "manual")
        return
    label, unit, lo, hi, dec, _ = MEASURES[key]
    v = float(value)
    if not lo <= v <= hi:
        raise BodyError(f"{label} should be between {lo:g} and {hi:g} {unit}")
    store.add_measurement(ts, key, round(v, dec), "manual")


def delete(store: Store, key: str, ts: int) -> bool:
    if key not in MEASURES:
        raise BodyError(f"unknown measure {key}")
    done = False
    for m in stored_metrics(key):
        done = store.delete_measurement(ts, m, "manual") or done
    return done


def entries(store: Store, tz: tzinfo, key: str) -> list[dict[str, Any]]:
    """One measure's entries, oldest first: {ts, date, value[, value2]}."""
    if key == "bp":
        dia = {m["ts"]: m["value"] for m in store.measurements("bp_dia")}
        rows = [
            {"ts": m["ts"], "value": m["value"], "value2": dia[m["ts"]]}
            for m in store.measurements("bp_sys")
            if m["ts"] in dia
        ]
    else:
        rows = [{"ts": m["ts"], "value": m["value"]} for m in store.measurements(key)]
    for r in rows:
        r["date"] = datetime.fromtimestamp(r["ts"], tz).date().isoformat()
    return rows


def all_entries(store: Store, tz: tzinfo) -> list[dict[str, Any]]:
    """Every hand-entered measure, newest first, for the Body page's list."""
    out = []
    for key, (label, unit, *_rest) in MEASURES.items():
        for e in entries(store, tz, key):
            out.append({**e, "key": key, "label": label, "unit": unit})
    out.sort(key=lambda e: e["ts"], reverse=True)
    return out


def definitions() -> list[dict[str, Any]]:
    return [
        {"key": k, "label": label, "unit": unit, "min": lo, "max": hi, "decimals": dec, "group": group}
        for k, (label, unit, lo, hi, dec, group) in MEASURES.items()
    ]


# ------------------------------------------------------------------ ratings


def bmi(weight_kg: float, height_cm: float) -> float:
    return weight_kg / (height_cm / 100) ** 2


def rate_bmi(v: float) -> str:
    if 18.5 <= v < 25:
        return "good"
    return "low" if v >= 30 else "fair"


def rate_waist(cm: float, sex: str | None) -> str | None:
    if sex not in ("male", "female"):
        return None
    first, second = (94, 102) if sex == "male" else (80, 88)
    return "good" if cm < first else "fair" if cm < second else "low"


def bp_category(sys_: float, dia: float) -> str:
    if sys_ >= 140 or dia >= 90:
        return "Stage 2 high blood pressure"
    if sys_ >= 130 or dia >= 80:
        return "Stage 1 high blood pressure"
    if sys_ >= 120:
        return "Elevated"
    return "Normal"


def rate_bp(sys_: float, dia: float) -> str:
    cat = bp_category(sys_, dia)
    return "good" if cat == "Normal" else "fair" if cat == "Elevated" else "low"


def rate_lab(key: str, v: float) -> tuple[str, str]:
    """(rating, category) for a blood test."""
    if key == "hba1c":
        return ("good", "Normal") if v < 5.7 else ("fair", "Prediabetes range") if v < 6.5 else ("low", "Diabetes range")
    if key == "glucose_fasting":
        return ("good", "Normal") if v < 5.6 else ("fair", "Prediabetes range") if v < 7.0 else ("low", "Diabetes range")
    if key == "ldl":
        if v < 2.6:
            return "good", "Optimal"
        if v < 3.4:
            return "fair", "Near optimal"
        if v < 4.1:
            return "fair", "Borderline high"
        return ("low", "High") if v < 4.9 else ("low", "Very high")
    if key == "hdl":
        return ("low", "Low") if v < 1.0 else ("good", "High (protective)") if v >= 1.6 else ("good", "Normal")
    if key == "triglycerides":
        if v < 1.7:
            return "good", "Normal"
        if v < 2.3:
            return "fair", "Borderline high"
        return ("low", "High") if v < 5.6 else ("low", "Very high")
    raise BodyError(f"unknown blood test {key}")


LAB_TARGETS = {
    "hba1c": "under 5.7%",
    "glucose_fasting": "under 5.6 mmol/L",
    "ldl": "under 2.6 mmol/L",
    "hdl": "1.0 mmol/L or more",
    "triglycerides": "under 1.7 mmol/L",
}
LAB_SOURCES = {
    "hba1c": ["ada_diagnosis"],
    "glucose_fasting": ["ada_diagnosis"],
    "ldl": ["ncep_atp3"],
    "hdl": ["ncep_atp3"],
    "triglycerides": ["ncep_atp3"],
}
LAB_RULES = {
    "hba1c": "The American Diabetes Association's ranges: under 5.7% is normal (on track), 5.7–6.4% is the prediabetes range (fair) and 6.5% or more the diabetes range (needs attention). A diagnosis needs a doctor and usually a repeat test.",
    "glucose_fasting": "The American Diabetes Association's ranges for glucose after at least 8 hours without food: under 5.6 mmol/L is normal, 5.6–6.9 the prediabetes range and 7.0 or more the diabetes range. A diagnosis needs a doctor and usually a repeat test.",
    "ldl": "The US National Cholesterol Education Program's classes (converted from mg/dL): under 2.6 mmol/L optimal (on track), 2.6–4.0 near optimal to borderline high (fair), 4.1 or more high (needs attention). Your own target depends on your overall risk, which your doctor can work out.",
    "hdl": "The US National Cholesterol Education Program's classes (converted from mg/dL): under 1.0 mmol/L counts as low (needs attention); 1.6 or more is high and counts in your favour.",
    "triglycerides": "The US National Cholesterol Education Program's classes (converted from mg/dL), from a fasting test: under 1.7 mmol/L normal, 1.7–2.2 borderline high (fair), 2.3 or more high (needs attention).",
}
