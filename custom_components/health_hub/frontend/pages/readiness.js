// Readiness: this morning's score and what went into it, or the trend over a period.

import { C } from "../charts.js";
import { dur, h, isNum, mean, shortDate } from "../util.js";
import { scoreColor, tile, why } from "../parts.js";
import { PART_NAMES, lateText, readinessCard } from "./common.js";
import { dayBars, dayLine } from "./trend.js";

export async function load(app) {
  const s = app.state;
  if (s.period === "day") return { mode: "day", d: await app.get({ type: "health_hub/day", date: s.date }) };
  const r = app.range;
  return { mode: "range", data: await app.get({ type: "health_hub/range", start: r.start, end: r.end }) };
}

export function render(app, data) {
  if (data.mode === "day") {
    const d = data.d;
    return `<div class="row">
        <div style="flex:1 1 360px;min-width:0;display:flex">${readinessCard(app, d)}</div>
        <div style="flex:2 1 480px;min-width:0;display:flex">${partsCard(app, d)}</div>
      </div>
      <article class="card"><div class="head"><h2>Last 14 days</h2><span class="tiny muted">Click a day to open it</span></div>
        ${dayBars(app, d.recent, "readiness", { max: 100, ticks: [0, 50, 100], colorFn: scoreColor, goto: "readiness", label: "Readiness for the last 14 days" })}</article>`;
  }
  const days = data.data.days;
  const vals = days.filter((d) => isNum(d.readiness));
  const best = vals.reduce((a, d) => (!a || d.readiness > a.readiness ? d : a), null);
  const worst = vals.reduce((a, d) => (!a || d.readiness < a.readiness ? d : a), null);
  const avg = mean(days.map((d) => d.readiness));
  return `<section class="grid small">
      ${tile("Average readiness", isNum(avg) ? Math.round(avg) : "–", `${vals.length} mornings scored`, scoreColor(avg))}
      ${tile("Best", best ? best.readiness : "–", best ? shortDate(best.date) : "")}
      ${tile("Lowest", worst ? worst.readiness : "–", worst ? shortDate(worst.date) : "")}
    </section>
    <article class="card"><div class="head"><h2>Readiness</h2><span class="tiny muted">Click a day to open it</span></div>
      ${dayBars(app, days, "readiness", { max: 100, ticks: [0, 50, 100], colorFn: scoreColor, goto: "readiness", label: "Readiness per day" })}</article>
    <section class="grid">
      <article class="card"><div class="head"><h2>Resting heart rate</h2></div>${dayLine(app, days, "rhr", { unit: " bpm" })}</article>
      <article class="card"><div class="head"><h2>Overnight stress</h2><span class="tiny muted">Band nights only</span></div>${dayLine(app, days, (d) => d.night && d.night.overnight ? d.night.overnight.stress_avg : null, { color: C.amber })}</article>
    </section>`;
}

function partsCard(app, d) {
  const r = d.readiness;
  if (!r) return `<article class="card" style="flex:1"><h2>What went into it</h2><p class="empty">No score this morning.</p></article>`;
  const b = d.baseline || {};
  const p = r.parts;
  const night = d.sleep.night;
  const rows = [];
  if (p.sleep) rows.push(["Sleep", p.sleep, `Last night's sleep score was ${Math.round(p.sleep.s * 100)}${night ? ` (${dur(night.asleep_min)} asleep)` : ""}.`]);
  if (p.resting_hr) rows.push(["Resting heart rate", p.resting_hr, `${Math.round(p.resting_hr.value)} bpm against your usual ${Math.round(b.rhr)}: ${Math.abs(p.resting_hr.diff) < 1 ? "about the same" : `${Math.abs(p.resting_hr.diff).toFixed(0)} ${p.resting_hr.diff < 0 ? "lower, which helps" : "higher, which lowers the score"}`}.`]);
  else rows.push(["Resting heart rate", null, "Not enough days yet to know your usual (needs 5)."]);
  if (p.overnight_stress) rows.push(["Overnight stress", p.overnight_stress, `${Math.round(p.overnight_stress.value)} against your usual ${Math.round(b.stress)}: ${Math.abs(p.overnight_stress.diff) < 1 ? "about the same" : `${Math.abs(p.overnight_stress.diff).toFixed(0)} ${p.overnight_stress.diff < 0 ? "lower, which helps" : "higher, which lowers the score"}`}.`]);
  else rows.push(["Overnight stress", null, "Needs 5 nights with the band to know your usual. Until then it's left out."]);
  if (p.timing) rows.push(["Sleep timing", p.timing, `Fell asleep ${lateText(p.timing.late_min)} against your ${app.settings.bed_target} target (allowing 15 minutes to fall asleep).`]);
  if (p.load) rows.push(["Yesterday's load", p.load, `Yesterday's load was ${p.load.value}; only loads above 70 lower readiness.`]);
  return `<article class="card" style="flex:1">
    <h2>What went into it</h2>
    <div class="scroll"><table>
      <thead><tr><th>Part</th><th>Weight</th><th>Score</th><th>Why</th></tr></thead>
      <tbody>${rows
        .map(([name, part, text]) => `<tr><td style="white-space:nowrap">${h(name)}</td><td>${part ? part.weight + "%" : "–"}</td><td style="color:${part ? (part.s >= 0.6 ? "var(--teal)" : "var(--amber)") : "var(--muted)"}">${part ? Math.round(part.s * 100) : "left out"}</td><td class="soft">${h(text)}</td></tr>`)
        .join("")}</tbody>
    </table></div>
    ${why(app, {
      rule: "Readiness is a weighted average of these parts. When a part can't be worked out, it's left out and the others re-weighted, so the score is always out of 100.",
      note: "Health Hub's own formula, in the spirit of recovery scores from other trackers. Overnight stress stands in for heart-rate variability, which the band doesn't export.",
    }, { key: "why-readiness-table" })}
  </article>`;
}
