// Settings: goals, targets and the figures the calculations need.

import { h, isNum } from "../util.js";

export const usesPeriod = false;
export const title = () => "Settings";

export async function load(app) {
  await app.refreshInfo();
  return { s: app.settings, info: app.info };
}

const hm = (min) => ({ h: Math.floor(min / 60), m: min % 60 });

export function render(app, data) {
  const s = data.s;
  const goal = hm(s.sleep_goal_min);
  const field = (name, label, attrs, hint = "") => `<label>${h(label)}<input name="${name}" ${attrs}>${hint ? `<span class="hint">${h(hint)}</span>` : ""}</label>`;
  const v = (x) => (isNum(x) ? x : x || "");
  return `<form class="card" data-submit="save" style="gap:20px">
      <h2>Goals</h2>
      <div class="settings" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px">
        ${field("steps_goal", "Steps a day", `type="number" min="500" max="50000" step="500" value="${s.steps_goal}"`)}
        <label>Sleep a night<span class="inline"><input name="sleep_h" type="number" min="4" max="12" value="${goal.h}" style="width:80px" aria-label="Hours"> h <input name="sleep_m" type="number" min="0" max="59" step="5" value="${goal.m}" style="width:80px" aria-label="Minutes"> m</span><span class="hint">Time asleep, not time in bed.</span></label>
        ${field("bed_target", "In bed by", `type="time" value="${h(s.bed_target)}"`)}
        ${field("wake_target", "Wake at", `type="time" value="${h(s.wake_target)}"`)}
        ${field("weight_goal_kg", "Goal weight (kg)", `type="number" min="30" max="300" step="0.1" value="${v(s.weight_goal_kg)}"`, "Leave empty for no goal.")}
      </div>
      <h2>Training</h2>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px" class="settings">
        ${field("gym_per_week", "Gym sessions a week", `type="number" min="0.5" max="14" step="0.5" value="${s.gym_per_week}"`)}
        ${field("compex_per_week", "Compex sessions a week", `type="number" min="0.5" max="14" step="0.5" value="${s.compex_per_week}"`)}
        ${field("block_weeks", "Weeks in a block", `type="number" min="1" max="12" value="${s.block_weeks}"`, "Rewards are counted at the end of each block.")}
        ${field("block_anchor", "Blocks count from (a Monday)", `type="date" value="${h(s.block_anchor || "")}"`, "Changing this moves every block.")}
      </div>
      <h2>For heart-rate zones and load</h2>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px" class="settings">
        ${field("age", "Age", `type="number" min="10" max="110" value="${v(s.age)}"`, "Only used to estimate your maximum heart rate (208 − 0.7 × age).")}
        ${field("max_hr", "Maximum heart rate (bpm)", `type="number" min="100" max="230" value="${v(s.max_hr)}"`, `Overrides the estimate. In use now: ${s.effective_max_hr} bpm.`)}
      </div>
      <div class="inline"><button class="btn" type="submit">Save settings</button><span class="small muted">Health Hub ${h(data.info.version)} · time zone ${h(data.info.time_zone)}</span></div>
    </form>
    <section class="card"><h2>Where the numbers come from</h2>
      <p class="small soft">Your band's readings arrive hourly from the Health Hub phone app. Minute-by-minute detail is kept for the number of days set in Health Hub's options; hourly and daily figures are kept for good. Readiness, sleep score, day load and energy are Health Hub's own calculations, explained under "Why?" wherever they appear. The daily review is written by Claude through the Health Hub Reviewer add-on.</p>
    </section>`;
}

export const actions = {
  save: async (app, data) => {
    const changes = {
      steps_goal: Number(data.steps_goal),
      sleep_goal_min: Number(data.sleep_h) * 60 + Number(data.sleep_m || 0),
      bed_target: data.bed_target,
      wake_target: data.wake_target,
      weight_goal_kg: data.weight_goal_kg === "" ? null : Number(data.weight_goal_kg),
      gym_per_week: Number(data.gym_per_week),
      compex_per_week: Number(data.compex_per_week),
      block_weeks: Number(data.block_weeks),
      age: data.age === "" ? null : Number(data.age),
      max_hr: data.max_hr === "" ? null : Number(data.max_hr),
    };
    if (data.block_anchor) changes.block_anchor = data.block_anchor;
    if (changes.weight_goal_kg !== null && !app.settings.weight_goal_set) changes.weight_goal_set = app.today;
    await app.call({ type: "health_hub/settings/set", changes });
    await app.refreshInfo();
    app.toast("Settings saved.");
    await app.render(true);
  },
};
