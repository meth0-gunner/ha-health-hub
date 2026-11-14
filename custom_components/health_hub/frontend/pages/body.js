// Body: weigh-ins, the trend and the goal.

import { C, axis, dotLayer, dots, hline, hoverable, line, scale, stroke, wide } from "../charts.js";
import { h, isNum, num, shortDate } from "../util.js";
import { tile, why } from "../parts.js";

export const usesPeriod = true;

export async function load(app) {
  const [d, m] = await Promise.all([app.get({ type: "health_hub/day", date: app.state.date }), app.get({ type: "health_hub/measures" })]);
  return { w: d.weight, m };
}

export function render(app, data) {
  const w = data.w;
  const s = app.settings;
  const r = app.range;
  const all = w.entries;
  const showAll = app.state.period === "day";
  const shown = showAll ? all : all.filter((e) => e.date >= r.start && e.date <= r.end);
  return `<div class="row">
      <article class="card" style="flex:2 1 560px">
        <div class="head"><h2>Weight</h2><span class="tiny muted">${showAll ? "All weigh-ins" : "Weigh-ins in this period"}${isNum(s.weight_goal_kg) ? " · dashed line: goal" : ""}</span></div>
        ${chart(shown, s.weight_goal_kg)}
      </article>
      <article class="card" style="flex:1 1 300px">
        <h2>Log a weigh-in</h2>
        <form class="settings" data-submit="weight" style="grid-template-columns:1fr">
          <label>Weight (kg)<input name="kg" type="number" step="0.1" min="20" max="400" inputmode="decimal" required></label>
          <label>Date<input name="date" type="date" value="${h(app.state.date)}" max="${h(app.today)}"></label>
          <button class="btn" type="submit">Log weight</button>
        </form>
        <h2 style="margin-top:8px">Goal</h2>
        <form class="settings" data-submit="goal" style="grid-template-columns:1fr">
          <label>Goal weight (kg)<input name="weight_goal_kg" type="number" step="0.1" min="30" max="300" value="${isNum(s.weight_goal_kg) ? s.weight_goal_kg : ""}"></label>
          <label>Counting from<input name="weight_goal_set" type="date" value="${h(s.weight_goal_set || "")}" max="${h(app.today)}"><span class="hint">"Down since you set the goal" counts from your last weigh-in on or before this date.</span></label>
          <button class="btn" type="submit">Save goal</button>
        </form>
      </article>
    </div>
    <section class="grid small">
      ${tile("Latest", w.latest ? `${num(w.latest.kg, 1)} kg` : "–", w.latest ? shortDate(w.latest.date, true) : "")}
      ${tile("Over 30 days", isNum(w.month_change_kg) ? `${w.month_change_kg > 0 ? "+" : w.month_change_kg < 0 ? "−" : "±"}${num(Math.abs(w.month_change_kg), 1)} kg` : "–", "")}
      ${tile("Since setting the goal", w.since_goal ? `${w.since_goal.change_kg > 0 ? "+" : w.since_goal.change_kg < 0 ? "−" : "±"}${num(Math.abs(w.since_goal.change_kg), 1)} kg` : "–", w.since_goal ? `from ${num(w.since_goal.start_kg, 1)} kg` : "Set a goal and a start date")}
      ${tile("To go", w.latest && isNum(w.goal) ? `${num(Math.max(0, w.latest.kg - w.goal), 1)} kg` : "–", isNum(w.progress) ? `${Math.round(w.progress * 100)}% of the way` : "")}
      ${tile("BMI", w.latest && isNum(s.height_cm) ? num(w.latest.kg / (s.height_cm / 100) ** 2, 1) : "–", isNum(s.height_cm) ? `at ${s.height_cm} cm · 18.5–24.9 is the healthy range` : "Add your height in Settings")}
    </section>
    ${measuresCard(app, data.m)}
    <article class="card"><div class="head"><h2>Weigh-ins</h2><span class="tiny muted">${shown.length} shown</span></div>
      ${shown.length ? `<div class="scroll" style="max-height:420px;overflow-y:auto"><table><thead><tr><th>Date</th><th>Weight</th><th>From</th><th></th></tr></thead><tbody>${shown
        .slice()
        .reverse()
        .map((e) => `<tr><td>${h(shortDate(e.date, true))}</td><td>${num(e.kg, 1)} kg</td><td class="muted">${e.source === "manual" ? "You" : e.source === "fitbit" ? "Fitbit history" : h(e.source)}</td><td>${e.source === "manual" ? `<button class="btn" style="min-height:32px" data-action="del" data-arg="${e.ts}">Delete</button>` : ""}</td></tr>`)
        .join("")}</tbody></table></div>` : `<p class="empty">No weigh-ins in this period.</p>`}
      ${why(app, { rule: "Weigh-ins are entered here, with the Log weight action, or imported from your Fitbit history. They also go into Home Assistant's long-term statistics as health_hub:weight.", note: "Daily weight moves with water and food, so the trend over weeks says more than any one day." }, { key: "why-weight" })}
    </article>`;
}

function measuresCard(app, m) {
  const defs = Object.fromEntries(m.definitions.map((d) => [d.key, d]));
  const blood = m.definitions.filter((d) => d.group === "blood");
  const date = `<label>Date<input name="date" type="date" value="${h(app.state.date)}" max="${h(app.today)}"></label>`;
  const fmtEntry = (e) => (e.key === "bp" ? `${num(e.value, 0)}/${num(e.value2, 0)} mmHg` : `${num(e.value, defs[e.key].decimals)} ${h(e.unit)}`);
  return `<article class="card">
      <div class="head"><h2>Waist, blood pressure and blood tests</h2><a href="/health/longevity" data-action="page" data-arg="longevity" class="small">See them rated on Longevity ›</a></div>
      <div class="measure-forms">
        <form class="settings" data-submit="measure" style="grid-template-columns:1fr">
          <input type="hidden" name="key" value="waist_cm">
          <label>Waist (cm)<input name="value" type="number" step="0.5" min="40" max="200" inputmode="decimal" required><span class="hint">Midway between your lowest rib and the top of your hip bone, breathing out.</span></label>
          ${date}
          <button class="btn" type="submit">Add waist</button>
        </form>
        <form class="settings" data-submit="measure" style="grid-template-columns:1fr">
          <input type="hidden" name="key" value="bp">
          <label>Blood pressure (mmHg)<span class="inline"><input name="value" type="number" min="70" max="260" required style="width:90px" aria-label="Top number (systolic)" placeholder="top"> / <input name="value2" type="number" min="40" max="160" required style="width:90px" aria-label="Bottom number (diastolic)" placeholder="bottom"></span><span class="hint">Seated and rested for 5 minutes.</span></label>
          ${date}
          <button class="btn" type="submit">Add blood pressure</button>
        </form>
        <form class="settings" data-submit="measure" style="grid-template-columns:1fr">
          <label>Blood test<select name="key">${blood.map((d) => `<option value="${d.key}">${h(d.label)} (${h(d.unit)})</option>`).join("")}</select></label>
          <label>Result<input name="value" type="number" step="0.01" min="0.2" max="30" inputmode="decimal" required><span class="hint">Copy it from your results; cholesterol and glucose in mmol/L, HbA1c in %.</span></label>
          ${date}
          <button class="btn" type="submit">Add result</button>
        </form>
      </div>
      ${m.entries.length ? `<div class="scroll" style="max-height:360px;overflow-y:auto"><table><thead><tr><th>Date</th><th>Measure</th><th>Value</th><th></th></tr></thead><tbody>${m.entries
        .map((e) => `<tr><td>${h(shortDate(e.date, true))}</td><td>${h(e.label)}</td><td>${fmtEntry(e)}</td><td><button class="btn" style="min-height:32px" data-action="delmeasure" data-arg="${h(e.key)}:${e.ts}">Delete</button></td></tr>`)
        .join("")}</tbody></table></div>` : `<p class="empty">Nothing added yet.</p>`}
    </article>`;
}

function chart(entries, goal) {
  if (entries.length < 2) return `<p class="empty">${entries.length ? "One weigh-in so far; the chart starts with the second." : "No weigh-ins yet."}</p>`;
  const t0 = entries[0].ts;
  const t1 = entries[entries.length - 1].ts;
  const W = 800;
  const H = 200;
  const sx = scale(t0, t1, 6, W - 6);
  const vals = entries.map((e) => e.kg).concat(isNum(goal) ? [goal] : []);
  const lo = Math.floor(Math.min(...vals) - 1);
  const hi = Math.ceil(Math.max(...vals) + 1);
  const sy = scale(lo, hi, H - 6, 6);
  const pts = entries.map((e) => [e.ts, e.kg]);
  const inner = (isNum(goal) ? hline(sy(goal), W, C.green, "6 5") : "") + stroke(line(pts, sx, sy), C.green, 2) + dotLayer(dots(pts, sx, sy), C.green, 6);
  const tips = entries.map((e) => [e.ts, `${shortDate(e.date, true)} · ${num(e.kg, 1)} kg`]);
  return `<div class="colchart"><div class="ylabels" style="height:${H}px">${[hi, (hi + lo) / 2, lo].map((v, i) => `<span style="top:${i * 50}%">${num(v, 0)}</span>`).join("")}</div>
    ${hoverable(wide(W, H, inner, { height: H, label: "Weight over time" }), t0, t1, tips)}
    <span></span>${axis([shortDate(entries[0].date, true), shortDate(entries[entries.length - 1].date, true)])}</div>`;
}

export const actions = {
  weight: async (app, data) => {
    const kg = Number(data.kg);
    if (!isNum(kg)) throw new Error("Enter your weight in kg");
    await app.call({ type: "health_hub/weight/log", kg, date: data.date || app.today });
    app.toast(`Logged ${num(kg, 1)} kg.`);
    await app.render(true);
  },
  goal: async (app, data) => {
    const changes = { weight_goal_kg: data.weight_goal_kg === "" ? null : Number(data.weight_goal_kg), weight_goal_set: data.weight_goal_set || (data.weight_goal_kg ? app.today : null) };
    await app.call({ type: "health_hub/settings/set", changes });
    await app.refreshInfo();
    app.toast("Goal saved.");
    await app.render(true);
  },
  measure: async (app, data) => {
    const msg = { type: "health_hub/measure/log", key: data.key, value: Number(data.value), date: data.date || app.today };
    if (data.value2 !== undefined) msg.value2 = Number(data.value2);
    if (!isNum(msg.value)) throw new Error("Enter a number");
    await app.call(msg);
    app.toast("Added.");
    await app.render(true);
  },
  delmeasure: async (app, arg) => {
    const [key, ts] = arg.split(":");
    await app.call({ type: "health_hub/measure/delete", key, ts: Number(ts) });
    app.toast("Deleted.");
    await app.render(true);
  },
  del: async (app, arg) => {
    await app.call({ type: "health_hub/weight/delete", ts: Number(arg) });
    app.toast("Weigh-in deleted.");
    await app.render(true);
  },
};
