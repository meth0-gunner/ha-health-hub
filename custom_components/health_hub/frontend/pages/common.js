// Day-level building blocks used by Overview and the detail pages.

import { C, area, axis, band, dotLayer, dots, fill, gauge, hline, hoverable, hypnogram, legend, line, meter, rects, ring, scale, stroke, vline, wide } from "../charts.js";
import { clock12, dur, h, hourLabel, isNum, num, mean } from "../util.js";
import { scoreColor, stat, why } from "../parts.js";

export const DAY_AXIS = ["12am", "3am", "6am", "9am", "12pm", "3pm", "6pm", "9pm", "12am"];

/** Quarter-hour averages from minute rows: column index → [[minute, value]]. */
export function quarters(minutes, col) {
  const sums = new Map();
  for (const m of minutes) {
    const v = m[col];
    if (!isNum(v)) continue;
    const q = Math.floor(m[0] / 15);
    const s = sums.get(q) || [0, 0];
    s[0] += v;
    s[1] += 1;
    sums.set(q, s);
  }
  const out = [];
  for (let q = 0; q < 96; q++) {
    const s = sums.get(q);
    out.push([q * 15 + 7.5, s ? s[0] / s[1] : null]);
  }
  return out;
}

// ------------------------------------------------------------ readiness

export const PART_NAMES = {
  sleep: "Sleep", resting_hr: "Resting heart rate", overnight_stress: "Overnight stress",
  timing: "Sleep timing", load: "Yesterday's load",
  duration: "Duration", restorative: "Deep and REM", interruptions: "Interruptions", heart: "Heart rate and stress",
};

export function readinessParts(r, night) {
  if (!r) return "";
  const p = r.parts;
  const items = [];
  if (p.sleep) items.push(meter("Sleep", p.sleep.s, night ? `${dur(night.asleep_min)}` : `${Math.round(p.sleep.s * 100)}`, colorFor(p.sleep.s)));
  if (p.resting_hr) items.push(meter("Resting heart rate", p.resting_hr.s, `${Math.round(p.resting_hr.value)} · ${signed(p.resting_hr.diff)} bpm`, colorFor(p.resting_hr.s)));
  if (p.overnight_stress) items.push(meter("Overnight stress", p.overnight_stress.s, `${Math.round(p.overnight_stress.value)} · ${signed(p.overnight_stress.diff)}`, colorFor(p.overnight_stress.s)));
  if (p.timing) items.push(meter("Sleep timing", p.timing.s, lateText(p.timing.late_min), colorFor(p.timing.s)));
  if (p.load) items.push(meter("Yesterday's load", p.load.s, p.load.s >= 0.99 ? "balanced" : `${p.load.value} · high`, colorFor(p.load.s)));
  return `<ul class="meters">${items.join("")}</ul>`;
}

export function readinessWhy(app, r, base, key) {
  const parts = r ? Object.entries(r.parts).map(([k, v]) => `${PART_NAMES[k]} ${v.weight}%`).join(", ") : "";
  const missing = r ? ["resting_hr", "overnight_stress"].filter((k) => !r.parts[k]).map((k) => PART_NAMES[k].toLowerCase()) : [];
  return why(app, {
    rule: `Health Hub's own score, comparing this morning with your previous 30 days. Parts used today: ${parts}. Each part scores 0–100%: resting heart rate and overnight stress lose points when above your usual and gain when below; sleep is last night's sleep score; timing is how close you fell asleep to your bedtime target.`,
    numbers: base ? `Your usual: resting heart rate ${fmt(base.rhr)} bpm${isNum(base.stress) ? `, overnight stress ${fmt(base.stress)}` : ""}.` : "",
    note: missing.length ? `Not enough band nights yet to compare ${missing.join(" and ")}; that part is left out until there are 5.` : "Overnight stress is the band's own score, which it works out from heart-rate variability, so it stands in for HRV here.",
  }, { key, center: true });
}

export function readinessCard(app, d, { big = true } = {}) {
  const r = d.readiness;
  const night = d.sleep.night;
  if (!r) {
    return `<article class="card"><div class="head"><h2>Readiness</h2><span class="small muted">${d.is_today ? "this morning" : ""}</span></div>
      <p class="empty">${night ? "Not enough data for a score yet." : "No sleep recorded last night, so there's no readiness score. Wear the band to bed and let it sync in the morning."}</p></article>`;
  }
  const color = scoreColor(r.score);
  return `<article class="card" style="gap:18px">
    <div class="head"><h2>Readiness</h2><span class="small muted">${d.is_today ? "this morning" : ""}</span></div>
    <div class="center" style="display:flex;flex-direction:column;gap:12px">
      ${ring(r.score / 100, { size: big ? 190 : 120, color, text: String(r.score), sub: r.label, subColor: color, width: 7, textSize: 26, label: `Readiness ${r.score} of 100, ${r.label}` })}
      <p class="lead center">${h(r.summary)}</p>
      ${readinessWhy(app, r, d.baseline, "why-readiness")}
    </div>
    ${readinessParts(r, night)}
  </article>`;
}

// ------------------------------------------------------------------ load

export function loadCard(app, d) {
  const l = d.load;
  const t = d.training;
  const logged = t && t.day_logs.length ? t.day_logs.map((x) => (x.kind === "gym" ? cap(x.variant) : "Compex")).join(", ") : "None";
  if (!l) {
    return `<article class="card"><div class="head"><h2>Day load</h2><span class="small muted">${d.is_today ? "so far today" : ""}</span></div>
      <p class="empty">No heart rate from the band ${d.is_today ? "yet today" : "on this day"}, so no load.</p>
      <div class="stats">${stat("Workouts logged", h(logged))}</div></article>`;
  }
  const [lo, hi] = l.range;
  let advice;
  if (l.score < lo) advice = `Recommended ${d.is_today ? "today" : ""}: <strong style="color:var(--amber)">${lo}–${hi}</strong>.${d.is_today && l.walk_min ? ` A ${l.walk_min}-minute brisk walk would get you there.` : ""}`;
  else if (l.score <= hi) advice = `In the recommended range of <strong style="color:var(--amber)">${lo}–${hi}</strong>.`;
  else advice = `Above the recommended ${lo}–${hi}. ${d.is_today ? "An easier rest of the day helps recovery." : ""}`;
  return `<article class="card">
    <div class="head"><h2>Day load</h2><span class="small muted">${d.is_today ? "so far today" : ""}</span></div>
    <div class="center" style="display:flex;justify-content:center">${gauge(l.score, l.range, { label: `Day load ${l.score} of 100; recommended ${lo} to ${hi}` })}</div>
    <p class="lead center">${advice}</p>
    ${why(app, {
      rule: "Each minute scores by how hard your heart is working, using heart-rate reserve (between your resting and maximum heart rate): 30% of reserve scores 1, up to 5 at 85% and above. Brisk walking (100+ steps a minute) scores at least 1. The day's total is shown on a 0–100 scale. The recommended range follows readiness: 75+ → 50–75, 55–74 → 35–60, under 55 → 15–40.",
      numbers: `Resting ${fmt(d.row.rhr || (d.baseline && d.baseline.rhr))} bpm · maximum ${l.max_hr} bpm (${l.max_hr_source === "default" ? "a default; set your age or maximum in Settings" : l.max_hr_source === "age" ? "estimated from your age" : "your setting"}). Minutes in zones 1–5: ${Object.values(l.zones).join(" · ")}.`,
      sources: l.max_hr_source === "age" ? ["max_hr"] : [],
    }, { key: "why-load", center: true })}
    <div class="stats">${stat("Active time", `${l.active_min} min`)}${stat("Peak heart rate", `${num(l.peak_hr)} bpm`)}${stat("Workouts logged", h(logged))}</div>
  </article>`;
}

// ---------------------------------------------------------------- energy

export function energyCard(app, d, { tall = false } = {}) {
  const e = d.energy;
  if (!e) {
    return `<article class="card"><div class="head"><h2>Energy</h2><span class="small muted">estimated</span></div><p class="empty">Needs band readings ${d.is_today ? "from today" : "from this day"}.</p></article>`;
  }
  const pts = e.series.map(([m, v]) => [m, v]);
  const W = 300, H = 90;
  const sx = scale(0, 1440, 0, W);
  const sy = scale(0, 100, H, 0);
  const chart = wide(W, H, fill(area(pts, sx, sy, 0), C.blue, 0.12) + stroke(line(pts, sx, sy), C.blue, 2), { height: tall ? 140 : 100, label: `Energy through the day, now ${e.now}` });
  const f = e.factors;
  const rows = [["Overnight recharge", f.recharge], ["Calm rest", f.calm], ["Stress", f.stress], ["Activity", f.activity], ["Time awake", f.awake]];
  const maxAbs = Math.max(1, ...rows.map(([, v]) => Math.abs(v)));
  const meters = rows
    .map(([name, v]) => meter(name, Math.abs(v) / maxAbs, `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)}`, v >= 0 ? C.blue : C.amber))
    .join("");
  let projection = "";
  if (d.is_today && d.sleep && d.sleep.tonight && isNum(d.now_min)) {
    const bed = toMin(d.sleep.tonight.asleep_by);
    let left = bed - d.now_min;
    if (left < 0) left += 1440;
    if (left > 0 && left < 18 * 60) {
      const quiet = Math.max(0, Math.round(e.now - 0.03 * left));
      projection = `<p class="lead">By ${h(clock12(d.sleep.tonight.asleep_by))}, a quiet evening would leave you near <strong style="color:var(--blue)">${quiet}</strong>.</p>`;
    }
  }
  return `<article class="card">
    <div class="head"><h2>Energy</h2><span class="small muted">estimated</span></div>
    <div style="display:flex;align-items:baseline;gap:10px"><span class="huge" style="color:var(--blue)">${e.now}</span><span class="small muted">${d.is_today ? "now" : "end of day"}${isNum(e.peak) ? ` · peaked at ${e.peak}${e.peak_time ? ` at ${clock12(e.peak_time)}` : ""}` : ""}</span></div>
    ${chart}
    ${axis(["12am", "6am", "12pm", "6pm", "12am"])}
    <ul class="meters" aria-label="What charged and drained your energy">${meters}</ul>
    ${projection}
    ${why(app, {
      rule: "An estimate, not a measurement, worked out minute by minute from the band's readings. It charges while you sleep (faster when overnight stress is low) and a little in calm, still stretches; it drains with time awake, stress above 25 and activity. The bars add up the changes since the start of last night.",
      note: "Health Hub's own model, along the lines of body-battery features in other trackers.",
    }, { key: "why-energy" })}
  </article>`;
}

// ------------------------------------------------------------ at a glance

export function glanceCard(app, d) {
  const g = d.glance;
  const minutes = g.minutes;
  const W = 960;
  const sx = scale(0, 1440, 0, W);
  const nowX = isNum(d.now_min) ? sx(d.now_min) : null;
  const now = (H) => (nowX !== null ? vline(nowX, H) : "");
  // heart rate
  let hr = quarters(minutes, 2);
  if (!hr.some((p) => isNum(p[1]))) hr = g.hourly.map((x) => [x.hour * 60 + 30, x.hr]);
  const hrVals = hr.map((p) => p[1]).filter(isNum);
  const bandPts = g.hr_band.map(([m, lo, hi]) => [m + 7.5, lo, hi]);
  const lo = Math.min(45, ...hrVals, ...bandPts.map((b) => b[1]));
  const hi = Math.max(130, ...hrVals, ...bandPts.map((b) => b[2]));
  const syH = scale(lo, hi, 120, 0);
  const hrSvg = wide(W, 120, fill(band(bandPts, sx, syH), C.roseBand) + stroke(line(hr, sx, syH), C.rose, 2) + now(120), { height: 120, label: "Heart rate through the day" });
  const hrTip = hr.filter((p) => isNum(p[1])).map(([m, v]) => [m, `${hourMin(m)} · ${Math.round(v)} bpm`]);
  // steps per hour, running total and pace line
  const perHour = Array(24).fill(0);
  for (const x of g.hourly) perHour[x.hour] += x.steps;
  const maxS = Math.max(600, ...perHour);
  const syS = scale(0, maxS, 72, 0);
  const goal = app.settings.steps_goal;
  let cum = 0;
  const cumPts = [[0, 0]];
  perHour.forEach((s, i) => {
    cum += s;
    if (!d.is_today || i * 60 <= d.now_min) cumPts.push([(i + 1) * 60, cum]);
  });
  const syC = scale(0, Math.max(goal, cum), 72, 0);
  const bars = rects(perHour.map((s, i) => [i * 60 + 6, i * 60 + 54, s, 0]).filter((b) => b[2] > 0), sx, syS);
  const pace = `M${sx(7 * 60).toFixed(1)} 72 L${sx(21 * 60).toFixed(1)} ${syC(goal).toFixed(1)}`;
  const stepsSvg = wide(W, 72, fill(bars, C.teal, 0.85) + stroke(pace, C.dim, 1.5, 'stroke-dasharray="4 4"') + stroke(line(cumPts, sx, syC), "#B2F5EA", 2) + now(72), { height: 72, label: "Steps per hour and running total" });
  const stepsTip = perHour.map((s, i) => [i * 60 + 30, `${hourLabel(i * 60)}–${hourLabel(i * 60 + 60)} · ${num(s)} steps`]);
  // stress
  const st = quarters(minutes, 3);
  const syT = scale(0, 100, 56, 0);
  const stBars = rects(st.filter((p) => isNum(p[1])).map(([m, v]) => [m - 6.5, m + 6.5, v, 0]), sx, syT);
  const stSvg = wide(W, 56, fill(stBars, C.amber, 0.85) + now(56), { height: 56, label: "Stress through the day" });
  const stTip = st.filter((p) => isNum(p[1])).map(([m, v]) => [m, `${hourMin(m)} · stress ${Math.round(v)}`]);
  const stressAvg = mean(st.map((p) => p[1]));
  // energy
  const e = d.energy;
  const eSvg = e ? wide(W, 56, stroke(line(e.series, sx, scale(0, 100, 56, 0)), C.blue, 2) + now(56), { height: 56, label: "Energy through the day" }) : "";
  const latestHr = [...hr].reverse().find((p) => isNum(p[1]));
  return `<article class="card" aria-label="${d.is_today ? "Today" : "The day"} at a glance" style="gap:10px">
    <div class="head"><h2>${d.is_today ? "Today" : "The day"} at a glance</h2>
      ${legend([[C.rose, "Heart rate"], [C.roseBand, "Your normal range"], [C.teal, "Steps"], [C.amber, "Stress"], [C.blue, "Energy"]])}</div>
    <div class="lanes">
      <span class="lab">Heart rate<b>${latestHr ? Math.round(latestHr[1]) : "–"}</b>bpm</span>
      ${hoverable(hrSvg, 0, 1440, hrTip)}
      <span class="lab">Steps<b>${num(d.row.steps)}</b></span>
      ${hoverable(stepsSvg, 0, 1440, stepsTip)}
      <span class="lab">Stress<b>${isNum(stressAvg) ? Math.round(stressAvg) : "–"}</b>avg</span>
      ${hoverable(stSvg, 0, 1440, stTip)}
      ${e ? `<span class="lab">Energy<b>${e.now}</b></span>${eSvg}` : ""}
      <span></span>${axis(DAY_AXIS)}
    </div>
    <p class="small muted">Steps: bars per hour; the light line is the running total, the dashed line the pace for ${num(goal)} by 9pm. The shaded band is your usual heart rate at that time of day over the last 30 days.</p>
  </article>`;
}

// ----------------------------------------------------------- last night

export function stageRows(night, base) {
  const usual = (v, b) => {
    if (!isNum(v) || !isNum(b) || b === 0) return ["", "var(--muted)"];
    if (v > b * 1.15) return ["above usual", "var(--teal)"];
    if (v < b * 0.85) return ["below usual", "var(--amber)"];
    return ["usual", "var(--muted)"];
  };
  const rows = [["Deep", C.deep, night.deep_min, base && base.deep], ["Light", C.light, night.light_min, base && base.light], ["REM", C.rem, night.rem_min, base && base.rem], ["Awake", C.awake, night.awake_min, base && base.awake]];
  return rows
    .map(([name, color, v, b]) => {
      const [txt, col] = name === "Awake" ? usualAwake(v, b) : usual(v, b);
      return `<dt class="muted"><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${color};margin-right:8px"></i>${name}</dt><dd style="margin:0;font-weight:600">${dur(v)}</dd><dd style="margin:0;color:${col}">${txt}</dd>`;
    })
    .join("");
}

function usualAwake(v, b) {
  if (!isNum(v) || !isNum(b)) return ["", "var(--muted)"];
  if (v > b * 1.3 + 5) return ["more than usual", "var(--amber)"];
  return ["usual", "var(--muted)"];
}

export function nightTimes(night, length) {
  const labels = [clock12(night.bed)];
  const startMin = toMin(night.bed);
  const steps = 4;
  for (let i = 1; i < steps; i++) {
    const m = (startMin + Math.round((length * i) / steps)) % 1440;
    labels.push(clock12(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`));
  }
  labels.push(clock12(night.wake));
  return labels;
}

export function lastNightCard(app, d) {
  const night = d.sleep.night;
  if (!night) {
    const naps = d.sleep.naps.length ? ` ${d.sleep.naps.length} nap${d.sleep.naps.length > 1 ? "s" : ""}, ${dur(d.sleep.naps.reduce((a, n) => a + n.asleep_min, 0))}.` : "";
    return `<article class="card"><div class="head"><h2>Last night</h2></div><p class="empty">No night's sleep recorded.${naps}</p></article>`;
  }
  const det = d.sleep.detail;
  const length = det ? det.length_min : Math.round((night.wake_ts - night.bed_ts) / 60);
  const lowest = det ? lowestHr(det.readings) : null;
  const chart = det && det.segments.length
    ? `<div style="display:grid;grid-template-columns:56px 1fr;gap:0 12px">
        <div class="lanes4" style="height:160px"><span>Awake</span><span>REM</span><span>Light</span><span>Deep</span></div>
        ${hypnogram(det.segments, length, { label: `Sleep stages from ${clock12(night.bed)} to ${clock12(night.wake)}` })}
        <span></span>${axis(nightTimes(night, length))}
      </div>`
    : `<p class="muted small">${night.source === "imported" ? "From your Fitbit history: totals only, no stage timeline." : "No stage timeline for this night."}</p>`;
  return `<article class="card" aria-label="Last night" style="gap:16px">
    <div class="head"><h2>${d.is_today ? "Last night" : "The night before"} <span class="muted" style="font-weight:400">· ${clock12(night.bed)} to ${clock12(night.wake)} · ${dur(night.asleep_min)} asleep</span></h2>
      <a href="/health/sleep" data-action="go" data-arg="sleep|day|${h(d.date)}" class="small" style="min-height:44px;display:inline-flex;align-items:center">Sleep details ›</a></div>
    <div class="row" style="gap:28px;align-items:stretch">
      <div style="flex:999 1 560px;min-width:0">${chart}</div>
      <dl style="flex:1 1 260px;margin:0;display:grid;grid-template-columns:1fr auto auto;gap:10px 16px;font-size:14px;align-content:center">
        ${stageRows(night, d.baseline)}
        ${lowest ? `<dt class="muted" style="border-top:1px solid var(--line);padding-top:10px">Lowest heart rate</dt><dd style="margin:0;font-weight:600;border-top:1px solid var(--line);padding-top:10px">${lowest.bpm} bpm</dd><dd style="margin:0;border-top:1px solid var(--line);padding-top:10px" class="muted">at ${clock12(addMin(night.bed, lowest.minute))}</dd>` : ""}
      </dl>
    </div>
  </article>`;
}

// ------------------------------------------------------------- helpers

export function lowestHr(readings) {
  let best = null;
  for (const r of readings) if (isNum(r[1]) && (!best || r[1] < best.bpm)) best = { bpm: r[1], minute: r[0] };
  return best;
}

export function toMin(hhmm) {
  const [a, b] = hhmm.split(":").map(Number);
  return a * 60 + b;
}

export function addMin(hhmm, minutes) {
  const m = (toMin(hhmm) + minutes) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function hourMin(minute) {
  const m = Math.floor(minute);
  return clock12(`${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
}

export function lateText(late) {
  if (!isNum(late)) return "–";
  if (Math.abs(late) <= 15) return "on time";
  return late > 0 ? `+${late} min late` : `${-late} min early`;
}

export const colorFor = (s) => (s >= 0.6 ? C.teal : C.amber);
const signed = (v) => (v > 0 ? `+${Math.round(v)}` : v < 0 ? `−${Math.abs(Math.round(v))}` : "±0");
const fmt = (v) => (isNum(v) ? Math.round(v) : "–");
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

export { dots, dotLayer, hline };
