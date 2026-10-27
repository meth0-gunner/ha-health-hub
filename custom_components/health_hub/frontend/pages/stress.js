// Stress and energy: the band's stress score through the day, and the energy estimate.

import { C, axis, columns, fill, hoverable, rects, scale, vline, wide } from "../charts.js";
import { h, isNum, mean } from "../util.js";
import { tile, why } from "../parts.js";
import { DAY_AXIS, energyCard, hourMin, quarters } from "./common.js";
import { dayBars, dayLine } from "./trend.js";

export async function load(app) {
  const s = app.state;
  if (s.period === "day") return { mode: "day", d: await app.get({ type: "health_hub/day", date: s.date }) };
  const r = app.range;
  return { mode: "range", data: await app.get({ type: "health_hub/range", start: r.start, end: r.end }) };
}

function stressWhy(app) {
  return why(app, {
    rule: "Stress is the band's own score from 1 to 100, which Xiaomi works out from heart-rate variability. Lower is calmer. Health Hub shows it as the band reports it.",
    note: "Health Hub colours readings by quarters of the scale (up to 25, 50, 75 and 100) and counts 25 or less as relaxed. Exercise raises the score too, so read it alongside your activity.",
  }, { key: "why-stress" });
}

export function render(app, data) {
  if (data.mode === "day") {
    const d = data.d;
    const st = quarters(d.glance.minutes, 3);
    const W = 960;
    const H = 140;
    const sx = scale(0, 1440, 0, W);
    const sy = scale(0, 100, H, 0);
    const colour = (v) => (v <= 25 ? C.teal : v <= 50 ? C.amber : v <= 75 ? "#F08A4B" : C.rose);
    const groups = {};
    for (const [m, v] of st) if (isNum(v)) (groups[colour(v)] ||= []).push([m - 6.5, m + 6.5, v, 0]);
    const inner = Object.entries(groups).map(([c, list]) => fill(rects(list, sx, sy), c, 0.9)).join("") + (isNum(d.now_min) ? vline(sx(d.now_min), H) : "");
    const tips = st.filter((p) => isNum(p[1])).map(([m, v]) => [m, `${hourMin(m - 7.5)} · ${Math.round(v)}`]);
    const vals = st.map((p) => p[1]).filter(isNum);
    const avg = mean(vals);
    const peak = vals.length ? st.reduce((a, p) => (isNum(p[1]) && (!a || p[1] > a[1]) ? p : a), null) : null;
    const night = d.sleep.night;
    const calm = vals.length ? Math.round((vals.filter((v) => v <= 25).length / vals.length) * 100) : null;
    return `<article class="card"><div class="head"><h2>Stress</h2><span class="small muted">every 15 minutes</span></div>
        ${vals.length ? `${hoverable(wide(W, H, inner, { height: H, label: "Stress through the day" }), 0, 1440, tips)}${axis(DAY_AXIS)}` : `<p class="empty">No stress readings on this day.</p>`}
        ${stressWhy(app)}
      </article>
      <section class="grid small">
        ${tile("Average", isNum(avg) ? Math.round(avg) : "–", "")}
        ${tile("Highest", peak ? Math.round(peak[1]) : "–", peak ? `around ${hourMin(peak[0] - 7.5)}` : "")}
        ${tile("Time relaxed", isNum(calm) ? `${calm}%` : "–", "Readings of 25 or less")}
        ${tile("Overnight", night && night.overnight && isNum(night.overnight.stress_avg) ? Math.round(night.overnight.stress_avg) : "–", d.baseline && isNum(d.baseline.stress) ? `Your usual ${Math.round(d.baseline.stress)}` : "")}
      </section>
      ${energyCard(app, d, { tall: true })}`;
  }
  const days = data.data.days;
  const windows = Array(12).fill(0);
  for (const d of days) if (isNum(d.stress_peak_window)) windows[d.stress_peak_window] += 1;
  const labels = ["12–2am", "2–4", "4–6", "6–8", "8–10", "10–12", "12–2pm", "2–4", "4–6", "6–8", "8–10", "10–12"];
  const peakChart = columns(windows.map((n, i) => ({ key: String(i), label: labels[i], segs: [{ v: n, color: C.amber }] })), { height: 140, yTicks: [0, Math.max(...windows)], label: "Days whose highest stress fell in each two-hour window" });
  return `<section class="grid">
      <article class="card"><div class="head"><h2>Average stress per day</h2><span class="tiny muted">Click a day to open it</span></div>
        ${dayBars(app, days, "stress_avg", { color: C.amber, max: 100, ticks: [0, 25, 50, 75, 100], goto: "stress", label: "Average stress per day" })}
        ${stressWhy(app)}</article>
      <article class="card"><div class="head"><h2>Overnight stress</h2><span class="tiny muted">Stands in for HRV; lower is better</span></div>
        ${dayLine(app, days, (d) => (d.night && d.night.overnight ? d.night.overnight.stress_avg : null), { color: C.amber })}</article>
    </section>
    <article class="card"><div class="head"><h2>When stress peaks</h2><span class="tiny muted">Days whose highest stress fell in each window</span></div>${peakChart}</article>`;
}

export const _ = h;
