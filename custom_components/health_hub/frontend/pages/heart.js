// Heart: heart rate through the day against your normal, resting heart rate, and old Fitbit HRV.

import { C, axis, band, fill, hoverable, line, scale, stroke, vline, wide, legend } from "../charts.js";
import { h, isNum, mean, num } from "../util.js";
import { sourceLinks, stat, tile, why } from "../parts.js";
import { DAY_AXIS, hourMin, lowestHr } from "./common.js";
import { dayLine } from "./trend.js";

export async function load(app) {
  const s = app.state;
  if (s.period === "day") return { mode: "day", d: await app.get({ type: "health_hub/day", date: s.date }) };
  const r = app.range;
  return { mode: "range", data: await app.get({ type: "health_hub/range", start: r.start, end: r.end }) };
}

export function render(app, data) {
  return data.mode === "day" ? renderDay(app, data.d) : renderRange(app, data.data.days);
}

function rhrWhy(app, base) {
  return why(app, {
    rule: "Resting heart rate is the band's own daily figure, worked out from your quietest readings. Health Hub compares it with your average over the previous 30 days.",
    numbers: base && isNum(base.rhr) ? `Your 30-day average: ${Math.round(base.rhr)} bpm.` : "",
    note: "For most adults a resting heart rate between 60 and 100 beats a minute is normal; fitter people are often lower.",
    sources: ["resting_hr"],
  }, { key: "why-rhr" });
}

function renderDay(app, d) {
  const g = d.glance;
  const pts = g.minutes.filter((m) => isNum(m[2])).map((m) => [m[0], m[2]]);
  const W = 1440;
  const H = 220;
  const sx = scale(0, 1440, 0, W);
  const bandPts = g.hr_band.map(([m, lo, hi]) => [m + 7.5, lo, hi]);
  const hourly = g.hourly.filter((x) => isNum(x.hr)).map((x) => [x.hour * 60 + 30, x.hr]);
  const series = pts.length ? pts : hourly;
  const vals = series.map((p) => p[1]).concat(bandPts.flatMap((b) => [b[1], b[2]]));
  const lo = Math.min(40, ...vals) - 2;
  const hi = Math.max(140, ...vals) + 4;
  const sy = scale(lo, hi, H, 0);
  // Break the line where readings are more than 10 minutes apart.
  const withGaps = [];
  for (let i = 0; i < series.length; i++) {
    if (i && series[i][0] - series[i - 1][0] > (pts.length ? 10 : 90)) withGaps.push([series[i][0] - 1, null]);
    withGaps.push(series[i]);
  }
  const now = isNum(d.now_min) ? vline(sx(d.now_min), H) : "";
  const svg = wide(W, H, fill(band(bandPts, sx, sy), C.roseBand) + stroke(line(withGaps, sx, sy), C.rose, 1.5) + now, { height: H, label: "Heart rate through the day against your usual range" });
  const tips = series.map(([m, v]) => [m, `${hourMin(m)} · ${Math.round(v)} bpm`]);
  const row = d.row;
  const night = d.sleep.night;
  const low = d.sleep.detail ? lowestHr(d.sleep.detail.readings) : null;
  const base = d.baseline || {};
  const diff = isNum(row.rhr) && isNum(base.rhr) ? row.rhr - base.rhr : null;
  return `<article class="card">
      <div class="head"><h2>Heart rate</h2>${legend([[C.rose, pts.length ? "Every minute" : "Hourly average (Fitbit)"], [C.roseBand, "Your usual at this time, last 30 days"]])}</div>
      <div style="display:grid;grid-template-columns:40px 1fr;gap:0 10px">
        <div class="ylabels" style="height:${H}px">${[hi, Math.round((hi + lo) / 2), lo].map((t, i) => `<span style="top:${i * 50}%">${Math.round(t)}</span>`).join("")}</div>
        ${hoverable(svg, 0, 1440, tips)}
        <span></span>${axis(DAY_AXIS)}
      </div>
    </article>
    <section class="grid small">
      ${tile("Resting heart rate", isNum(row.rhr) ? `${Math.round(row.rhr)} <span class="small muted" style="font-weight:400">bpm</span>` : "–", isNum(diff) ? `${Math.abs(diff) < 1 ? "about your usual" : `${Math.abs(diff).toFixed(0)} ${diff < 0 ? "below" : "above"} your usual ${Math.round(base.rhr)}`}` : "")}
      ${tile("Lowest overnight", low ? `${low.bpm} <span class="small muted" style="font-weight:400">bpm</span>` : night && night.overnight ? `${night.overnight.hr_min} bpm` : "–", night ? `Average overnight ${night.overnight ? Math.round(night.overnight.hr_avg) : "–"} bpm` : "")}
      ${tile("Day average", isNum(row.hr_avg) ? `${Math.round(row.hr_avg)} <span class="small muted" style="font-weight:400">bpm</span>` : "–", "")}
      ${tile("Peak", isNum(row.peak_hr) ? `${row.peak_hr} <span class="small muted" style="font-weight:400">bpm</span>` : "–", "")}
      ${isNum(row.hrv) ? tile("HRV (Fitbit)", `${num(row.hrv, 1)} <span class="small muted" style="font-weight:400">ms</span>`, "From your Fitbit history") : ""}
    </section>
    ${rhrWhy(app, base)}`;
}

function renderRange(app, days) {
  const base = mean(days.map((d) => d.rhr));
  const hasHrv = days.some((d) => isNum(d.hrv));
  const hasResp = days.some((d) => isNum(d.respiratory_rate));
  return `<section class="grid small">
      ${tile("Average resting heart rate", isNum(base) ? `${Math.round(base)} <span class="small muted" style="font-weight:400">bpm</span>` : "–", "")}
      ${tile("Lowest resting", Math.min(...days.map((d) => d.rhr).filter(isNum)) < Infinity ? `${Math.round(Math.min(...days.map((d) => d.rhr).filter(isNum)))} bpm` : "–", "")}
      ${tile("Highest resting", Math.max(...days.map((d) => d.rhr).filter(isNum)) > -Infinity ? `${Math.round(Math.max(...days.map((d) => d.rhr).filter(isNum)))} bpm` : "–", "")}
    </section>
    <section class="grid">
      <article class="card"><div class="head"><h2>Resting heart rate</h2><span class="tiny muted">Shaded: your 30-day usual ± 3 bpm</span></div>
        ${dayLine(app, days, "rhr", { unit: " bpm", bandFn: (d) => (d.baseline && isNum(d.baseline.rhr) ? [d.baseline.rhr - 3, d.baseline.rhr + 3] : null) })}
        ${rhrWhy(app, null)}</article>
      <article class="card"><div class="head"><h2>Lowest heart rate overnight</h2><span class="tiny muted">Band nights</span></div>
        ${dayLine(app, days, (d) => (d.night && d.night.overnight ? d.night.overnight.hr_min : null), { unit: " bpm" })}</article>
      ${hasHrv ? `<article class="card"><div class="head"><h2>Heart rate variability</h2><span class="tag">From Fitbit history</span></div>
        ${dayLine(app, days, "hrv", { color: C.violet, unit: " ms" })}
        <p class="small muted">The band doesn't export HRV, so this stops when you stopped wearing the Fitbit. Overnight stress (Stress & energy page) is the band's stand-in.</p></article>` : ""}
      ${hasResp ? `<article class="card"><div class="head"><h2>Breathing rate</h2><span class="tag">From Fitbit history</span></div>
        ${dayLine(app, days, "respiratory_rate", { color: C.blue, unit: " a min" })}</article>` : ""}
    </section>`;
}

export const _ = [h, sourceLinks, stat];
