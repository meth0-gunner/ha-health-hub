// Overview: scores, the daily review, goals, training, highlights, the day at a glance, last night.

import { C, ring } from "../charts.js";
import { clock12, dur, h, isNum, mean, num, shortDate } from "../util.js";
import { highlights, loadReview, reviewActions, reviewCard, scoreColor, stepsRing, tile, trainingActions, trainingSection, why } from "../parts.js";
import { energyCard, glanceCard, lastNightCard, loadCard, readinessCard, toMin } from "./common.js";
import { dayBars, dayLine } from "./trend.js";

export async function load(app) {
  const s = app.state;
  if (s.period === "day") {
    const [d, review] = await Promise.all([app.get({ type: "health_hub/day", date: s.date }), s.date === app.today ? loadReview(app) : null]);
    return { mode: "day", d, review };
  }
  const r = app.range;
  return { mode: "range", data: await app.get({ type: "health_hub/range", start: r.start, end: r.end }) };
}

export function render(app, data) {
  return data.mode === "day" ? renderDay(app, data.d, data.review) : renderRange(app, data.data);
}

function renderDay(app, d, review) {
  return `
    <section class="grid" aria-label="Scores">${readinessCard(app, d)}${loadCard(app, d)}${energyCard(app, d)}</section>
    ${d.is_today ? reviewCard(app, review) : ""}
    <section class="grid" aria-label="Goals">${stepsCard(app, d)}${sleepGoalCard(app, d)}${weightCard(app, d)}</section>
    ${trainingSection(app, d.training)}
    ${highlights(app, d.highlights)}
    ${glanceCard(app, d)}
    ${lastNightCard(app, d)}
  `;
}

function stepsCard(app, d) {
  const st = d.steps;
  const streak = st.current ? `Streak ${st.current} day${st.current === 1 ? "" : "s"} · best ${st.best}` : `No streak running · best ${st.best} day${st.best === 1 ? "" : "s"}`;
  return `<article class="card tight" style="flex-direction:row;align-items:center;gap:20px">
    ${stepsRing(st)}
    <div style="display:flex;flex-direction:column;gap:4px;min-width:0">
      <span class="small muted">Steps</span>
      <span class="num">${num(st.total)} <span class="small muted" style="font-weight:400">/ ${num(st.goal)}</span></span>
      <span class="small soft">${h(streak)}</span>
    </div>
  </article>`;
}

function sleepGoalCard(app, d) {
  const s = app.settings;
  const total = d.sleep.total_min;
  const night = d.sleep.night;
  const frac = s.sleep_goal_min ? total / s.sleep_goal_min : 0;
  const off = (actual, target) => {
    let diff = toMin(actual) - toMin(target);
    if (diff > 720) diff -= 1440;
    if (diff < -720) diff += 1440;
    return Math.abs(diff) > 30;
  };
  const times = night
    ? `Bed ${clock12(night.bed)} <span style="color:${off(night.bed, s.bed_target) ? "var(--amber)" : "var(--muted)"}">(target ${clock12(s.bed_target)})</span> · up ${clock12(night.wake)} <span style="color:${off(night.wake, s.wake_target) ? "var(--amber)" : "var(--muted)"}">(${clock12(s.wake_target)})</span>`
    : "No night recorded";
  const naps = d.sleep.naps.length ? ` · includes ${d.sleep.naps.length === 1 ? "a nap" : `${d.sleep.naps.length} naps`}` : "";
  return `<article class="card tight" style="flex-direction:row;align-items:center;gap:20px">
    ${ring(frac, { color: C.violet, text: `${Math.round(Math.min(frac, 9.99) * 100)}%`, label: `Sleep ${dur(total)} of ${dur(s.sleep_goal_min)}` })}
    <div style="display:flex;flex-direction:column;gap:4px;min-width:0">
      <span class="small muted">Sleep</span>
      <span class="num">${dur(total)} <span class="small muted" style="font-weight:400">/ ${dur(s.sleep_goal_min)}</span></span>
      <span class="small soft">${times}${naps}</span>
    </div>
  </article>`;
}

export function weightCard(app, d) {
  const w = d.weight;
  const s = app.settings;
  const latest = w.latest;
  const goal = isNum(w.goal) ? `<span class="small muted" style="font-weight:400">→ goal ${num(w.goal, 1)} kg</span>` : "";
  const bar = isNum(w.progress) ? `<div class="track" style="height:8px"><span style="height:8px;width:${Math.round(w.progress * 100)}%;background:var(--green, #9AE6B4)"></span></div>` : "";
  const notes = [];
  if (w.since_goal) notes.push(`${num(Math.abs(w.since_goal.change_kg), 1)} kg ${w.since_goal.change_kg <= 0 ? "down" : "up"} since you set the goal`);
  if (isNum(w.month_change_kg)) notes.push(`${w.month_change_kg > 0 ? "+" : w.month_change_kg < 0 ? "−" : "±"}${num(Math.abs(w.month_change_kg), 1)} kg over 30 days`);
  if (latest && latest.date !== app.today) notes.push(`last weighed ${shortDate(latest.date)}`);
  return `<article class="card tight" style="justify-content:center;gap:10px">
    <div class="head"><span class="small muted">Weight</span>${!isNum(s.weight_goal_kg) ? `<a href="/health/settings" data-action="page" data-arg="settings" class="small">Set a goal</a>` : ""}</div>
    <span class="num">${latest ? `${num(latest.kg, 1)} kg` : "No weigh-ins yet"} ${goal}</span>
    ${bar}
    ${notes.length ? `<span class="small soft">${h(notes.join(" · "))}</span>` : ""}
    <form class="inline" data-submit="weight"><label class="sr" for="kg">Weight in kg</label><input id="kg" name="kg" type="number" step="0.1" min="20" max="400" inputmode="decimal" placeholder="kg" style="width:96px" required><button class="btn" type="submit">Log weight</button></form>
  </article>`;
}

export const weightAction = async (app, data) => {
  const kg = Number(data.kg);
  if (!isNum(kg)) throw new Error("Enter your weight in kg");
  await app.call({ type: "health_hub/weight/log", kg, date: app.state.date });
  app.toast(`Logged ${num(kg, 1)} kg${app.state.date === app.today ? "" : ` for ${shortDate(app.state.date)}`}.`);
  await app.render(true);
};

export const actions = { ...reviewActions, ...trainingActions, weight: weightAction };

// ---------------------------------------------------------------- periods

function renderRange(app, data) {
  const days = data.days;
  const s = app.settings;
  const withData = days.filter((d) => d.steps || d.night);
  if (!withData.length) return `<section class="card"><p class="empty">No data in this period.</p></section>`;
  const ready = mean(days.map((d) => d.readiness));
  const sleepAvg = mean(days.map((d) => d.sleep_total_min || null));
  const steps = mean(days.filter((d) => d.date !== app.today).map((d) => d.steps || null));
  const met = days.filter((d) => d.steps >= s.steps_goal).length;
  const load = mean(days.map((d) => d.load));
  const rhr = mean(days.map((d) => d.rhr));
  return `
    <section class="grid small" aria-label="Averages">
      ${tile("Average readiness", isNum(ready) ? Math.round(ready) : "–", "", scoreColor(ready))}
      ${tile("Average sleep", dur(sleepAvg), `Goal ${dur(s.sleep_goal_min)} · naps included`)}
      ${tile("Average steps", num(steps), `Goal hit on ${met} of ${days.length} days`)}
      ${tile("Average day load", isNum(load) ? Math.round(load) : "–", "Band days only")}
      ${tile("Resting heart rate", isNum(rhr) ? `${Math.round(rhr)} <span class="small muted">bpm</span>` : "–", "Average")}
    </section>
    <section class="grid">
      <article class="card"><div class="head"><h2>Readiness</h2><span class="tiny muted">Click a day to open it</span></div>
        ${dayBars(app, days, "readiness", { max: 100, ticks: [0, 50, 100], colorFn: scoreColor, label: "Readiness per day" })}</article>
      <article class="card"><div class="head"><h2>Sleep</h2></div>
        ${dayBars(app, days, (d) => (d.sleep_total_min ? d.sleep_total_min / 60 : null), { color: C.violet, goal: s.sleep_goal_min / 60, max: 10, ticks: [0, 2, 4, 6, 8, 10], fmtY: (v) => `${v}h`, label: "Sleep per night" })}</article>
      <article class="card"><div class="head"><h2>Steps</h2></div>
        ${dayBars(app, days, "steps", { goal: s.steps_goal, fmtY: (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : v), label: "Steps per day" })}</article>
      <article class="card"><div class="head"><h2>Day load</h2><span class="tiny muted">Shaded: recommended range</span></div>
        ${dayBars(app, days, "load", { color: C.amber, max: 100, ticks: [0, 50, 100], whisker: (d) => (isNum(d.load) || d.readiness ? d.load_range : null), label: "Day load per day" })}</article>
      <article class="card"><div class="head"><h2>Resting heart rate</h2></div>
        ${dayLine(app, days, "rhr", { unit: " bpm", label: "Resting heart rate per day" })}</article>
    </section>
    ${why(app, { rule: "Averages count only days with data. Today is left out of the steps average because the day isn't over." }, { key: "why-range" })}
  `;
}
