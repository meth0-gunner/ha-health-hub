// Activity and load: steps, distance, active minutes and the day's load.

import { C, axis, fill, hoverable, line, meter, rects, scale, stroke, vline, wide } from "../charts.js";
import { h, hourLabel, isNum, mean, num, sum } from "../util.js";
import { stat, stepsRing, tile, why } from "../parts.js";
import { DAY_AXIS, loadCard } from "./common.js";
import { dayBars } from "./trend.js";

export async function load(app) {
  const s = app.state;
  if (s.period === "day") return { mode: "day", d: await app.get({ type: "health_hub/day", date: s.date }) };
  const r = app.range;
  return { mode: "range", data: await app.get({ type: "health_hub/range", start: r.start, end: r.end }) };
}

const ZONES = ["Zone 1 · light", "Zone 2 · moderate", "Zone 3 · moderate+", "Zone 4 · hard", "Zone 5 · maximum"];

export function render(app, data) {
  if (data.mode === "day") return renderDay(app, data.d);
  return renderRange(app, data.data.days);
}

function renderDay(app, d) {
  const row = d.row;
  const z = d.load && d.load.zones;
  const zMax = z ? Math.max(1, ...Object.values(z)) : 1;
  const mvpa = z ? z["2"] + z["3"] + z["4"] + z["5"] : null;
  return `<div class="row">
      <div style="flex:2 1 520px;min-width:0;display:flex">${stepsCard(app, d)}</div>
      <div style="flex:1 1 320px;min-width:0;display:flex">${loadCard(app, d)}</div>
    </div>
    <section class="grid">
      <article class="card"><h2>The day in numbers</h2>
        <div class="stats" style="border:0;padding:0">
          ${stat("Distance", `${num(row.distance_km, 2)} km`)}
          ${stat("Active calories", `${num(row.active_kcal)} kcal`)}
          ${stat("Moderate or harder", isNum(mvpa) ? `${mvpa} min` : "–")}
          ${stat("Peak heart rate", isNum(row.peak_hr) ? `${row.peak_hr} bpm` : "–")}
          ${stat("Band worn", isNum(row.worn_hours) ? `${num(row.worn_hours, 1)} h` : "–")}
        </div>
        ${row.sources.includes("imported") ? `<p class="tiny faint">Part of this day comes from your Fitbit history.</p>` : ""}
      </article>
      <article class="card"><h2>Time in heart-rate zones</h2>
        ${z ? `<ul class="meters">${Object.entries(z).map(([k, v], i) => meter(ZONES[i], v / zMax, `${v} min`, [C.teal, C.teal, C.amber, C.amber, C.rose][i])).join("")}</ul>` : `<p class="empty">No heart rate from the band on this day.</p>`}
        ${why(app, {
          rule: "Zones use heart-rate reserve, the gap between your resting and maximum heart rate: zone 1 from 30%, zone 2 from 45%, zone 3 from 60%, zone 4 from 75%, zone 5 from 85%. Zone 2 and above counts as moderate or harder.",
          numbers: d.load ? `Maximum heart rate ${d.load.max_hr} bpm (${d.load.max_hr_source === "default" ? "a default; set your age or maximum in Settings for better zones" : d.load.max_hr_source === "age" ? "estimated as 208 − 0.7 × age" : "your setting"}).` : "",
          sources: d.load && d.load.max_hr_source === "age" ? ["max_hr"] : [],
        }, { key: "why-zones" })}
      </article>
    </section>`;
}

function stepsCard(app, d) {
  const g = d.glance;
  const perHour = Array(24).fill(0);
  for (const x of g.hourly) perHour[x.hour] += x.steps;
  const W = 960;
  const H = 160;
  const sx = scale(0, 1440, 0, W);
  const maxS = Math.max(600, ...perHour);
  const sy = scale(0, maxS, H, 0);
  const goal = app.settings.steps_goal;
  let cum = 0;
  const cumPts = [[0, 0]];
  perHour.forEach((s, i) => { cum += s; if (!d.is_today || i * 60 <= d.now_min) cumPts.push([(i + 1) * 60, cum]); });
  const syC = scale(0, Math.max(goal, cum), H, 0);
  const bars = rects(perHour.map((s, i) => [i * 60 + 6, i * 60 + 54, s, 0]).filter((b) => b[2] > 0), sx, sy);
  const pace = `M${sx(7 * 60).toFixed(1)} ${H} L${sx(21 * 60).toFixed(1)} ${syC(goal).toFixed(1)}`;
  const now = isNum(d.now_min) ? vline(sx(d.now_min), H) : "";
  const svg = wide(W, H, fill(bars, C.teal, 0.85) + stroke(pace, C.dim, 1.5, 'stroke-dasharray="4 4"') + stroke(line(cumPts, sx, syC), "#B2F5EA", 2) + now, { height: H, label: "Steps per hour and running total" });
  const tips = perHour.map((s, i) => [i * 60 + 30, `${hourLabel(i * 60)}–${hourLabel(i * 60 + 60)} · ${num(s)} steps`]);
  const st = d.steps;
  return `<article class="card" style="flex:1">
    <div class="head"><h2>Steps</h2><span class="small muted">${st.current ? `Streak ${st.current} day${st.current === 1 ? "" : "s"} · ` : ""}best ${st.best}</span></div>
    <div style="display:flex;align-items:center;gap:20px">${stepsRing(st)}<span class="num">${num(st.total)} <span class="small muted" style="font-weight:400">/ ${num(st.goal)}</span></span></div>
    ${hoverable(svg, 0, 1440, tips)}${axis(DAY_AXIS)}
    <p class="small muted">Bars per hour; the light line is the running total; the dashed line is the pace for ${num(goal)} by 9pm.</p>
  </article>`;
}

function renderRange(app, days) {
  const s = app.settings;
  const full = days.filter((d) => d.date !== app.today);
  const total = sum(days.map((d) => d.steps));
  const avg = mean(full.map((d) => d.steps || null));
  const met = days.filter((d) => d.steps >= s.steps_goal).length;
  const mv = (d) => (d.zones ? d.zones["2"] + d.zones["3"] + d.zones["4"] + d.zones["5"] : null);
  const mvDays = days.filter((d) => isNum(mv(d)));
  const perWeek = mvDays.length ? (sum(mvDays.map(mv)) / mvDays.length) * 7 : null;
  return `<section class="grid small">
      ${tile("Steps", num(total), `${num(avg)} a day on average`)}
      ${tile("Goal hit", `${met} <span class="small muted" style="font-weight:400">of ${days.length} days</span>`, `Goal ${num(s.steps_goal)}`)}
      ${tile("Moderate or harder", isNum(perWeek) ? `${Math.round(perWeek)} <span class="small muted" style="font-weight:400">min a week</span>` : "–", mvDays.length && mvDays.length < 7 ? `From only ${mvDays.length} band day${mvDays.length === 1 ? "" : "s"} · WHO advice: 150–300` : "WHO advice: 150–300", isNum(perWeek) && mvDays.length >= 7 && perWeek < 150 ? C.amber : "")}
      ${tile("Distance", `${num(sum(days.map((d) => d.distance_km)), 1)} km`, "")}
    </section>
    ${why(app, {
      rule: "Moderate or harder: minutes in heart-rate zone 2 or above (45% of heart-rate reserve and up), averaged over the band days in this period and scaled to a week.",
      note: "The World Health Organization advises adults to do 150 to 300 minutes of moderate activity a week, or 75 to 150 minutes of vigorous activity, plus muscle-strengthening on two or more days.",
      sources: ["who_activity"],
    }, { key: "why-mvpa" })}
    <section class="grid">
      <article class="card"><div class="head"><h2>Steps</h2><span class="tiny muted">Click a day to open it</span></div>
        ${dayBars(app, days, "steps", { goal: s.steps_goal, fmtY: (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : v), goto: "activity", label: "Steps per day" })}</article>
      <article class="card"><div class="head"><h2>Day load</h2><span class="tiny muted">Shaded: recommended range</span></div>
        ${dayBars(app, days, "load", { color: C.amber, max: 100, ticks: [0, 50, 100], whisker: (d) => (isNum(d.load) ? d.load_range : null), goto: "activity", label: "Day load per day" })}</article>
      <article class="card"><div class="head"><h2>Moderate or harder minutes</h2></div>
        ${dayBars(app, days, mv, { color: C.teal, goto: "activity", label: "Moderate or harder minutes per day" })}</article>
      <article class="card"><div class="head"><h2>Distance</h2></div>
        ${dayBars(app, days, "distance_km", { color: C.blue, fmtY: (v) => `${v}`, goto: "activity", label: "Distance per day in km" })}</article>
    </section>`;
}

export const _ = h;
