// Sleep: tonight's bedtime, the week's nights, one night in full, and the long view.

import { C, area, axis, band, columns, dotLayer, dots, fill, hline, hoverable, hypnogram, legend, line, meter, rects, ring, scale, stroke, wide } from "../charts.js";
import { addDays, clock12, clockFromNoon, dayName, dur, h, isNum, mean, num, shortDate } from "../util.js";
import { highlights, loadReview, reviewCard, scoreColor, tile, why } from "../parts.js";
import { PART_NAMES, addMin, colorFor, lateText, lowestHr, nightTimes, stageRows } from "./common.js";
import { axisLabels } from "./trend.js";

let selected = null; // date of the night chosen in a period view

export async function load(app) {
  const s = app.state;
  if (s.period === "day") {
    const [d, review] = await Promise.all([app.get({ type: "health_hub/day", date: s.date }), s.date === app.today ? loadReview(app) : null]);
    return { mode: "day", d, review };
  }
  const r = app.range;
  const [range, history, review] = await Promise.all([
    app.get({ type: "health_hub/range", start: r.start, end: r.end }),
    app.get({ type: "health_hub/sleep_history" }),
    r.end === app.today ? loadReview(app) : null,
  ]);
  const withNight = range.days.filter((d) => d.night);
  if (!selected || selected < r.start || selected > r.end || !withNight.some((d) => d.date === selected)) {
    selected = withNight.length ? withNight[withNight.length - 1].date : null;
  }
  const night = selected ? await app.get({ type: "health_hub/night", date: selected }) : null;
  return { mode: "range", range, history, night, review };
}

export function render(app, data) {
  if (data.mode === "day") {
    const d = data.d;
    const nightData = { date: d.date, night: d.sleep.night, naps: d.sleep.naps, detail: d.sleep.detail, oxygen: d.sleep.oxygen, baseline: d.baseline };
    return `${d.sleep.tonight ? tonightCard(app, d.sleep.tonight) : ""}
      ${nightSection(app, nightData)}
      ${data.review ? reviewCard(app, data.review, { topics: ["sleep", "oxygen", "recovery"], compact: true }) : ""}`;
  }
  const { range, history, night, review } = data;
  const days = range.days;
  const tonight = range.last === app.today ? tonightFromRange(app, range) : null;
  return `${tonight ? tonightCard(app, tonight) : ""}
    ${summaryTiles(app, days, range.debt_min)}
    <div class="row">
      <article class="card" style="flex:3 1 560px" aria-label="Sleep per night">
        <div class="head"><h2>Sleep per night</h2>${legend([[C.deep, "Deep"], [C.light, "Light"], [C.rem, "REM"], [C.awake, "Awake"], [C.nap, "Nap"], [C.text, "Goal", "dash"]])}</div>
        ${perNight(app, days)}
        <p class="tiny faint">Numbers above the bars: Health Hub sleep score. Click a night to open it below.</p>
      </article>
      ${days.length <= 45 ? `<article class="card" style="flex:2 1 380px" aria-label="Bed and wake times"><div class="head"><h2>Bed and wake times</h2>${legend([["#22303A", "Target window"]])}</div>${bedWake(app, days)}</article>` : ""}
    </div>
    ${highlights(app, range.sleep_highlights, "No sleep patterns stand out yet. They appear once there are a few weeks of nights to compare.")}
    ${review ? reviewCard(app, review, { topics: ["sleep", "oxygen", "recovery"], compact: true }) : ""}
    ${night ? nightSection(app, night) : ""}
    ${longTerm(app, history)}`;
}

export const actions = {
  night: async (app, arg) => {
    selected = arg;
    await app.render(true);
  },
};

// --------------------------------------------------------------- tonight

function tonightCard(app, t) {
  const why1 = why(app, {
    rule: `Wake target ${clock12(t.wake)}, less your ${dur(t.goal_min)} sleep goal${t.catch_up_min ? `, less ${t.catch_up_min} minutes to pay back a third of this week's ${dur(t.debt_min)} sleep debt (capped at 30)` : ""}. Wind-down starts 30 minutes earlier.`,
    note: "Your goal and wake time are in Settings. Adults are advised to sleep 7 hours or more a night regularly.",
    sources: ["aasm_sleep_duration"],
  }, { key: "why-tonight" });
  return `<article class="card night" aria-label="Tonight" style="flex-direction:row;flex-wrap:wrap;align-items:center;gap:20px">
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#C4A8FF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path></svg>
    <div style="flex:1 1 420px;min-width:0;display:flex;flex-direction:column;gap:4px">
      <span class="small" style="color:#B8AEE0">Tonight</span>
      <span style="font-size:24px;font-weight:600">Aim to be asleep by <span style="color:#C4A8FF">${clock12(t.asleep_by)}</span></span>
      <span class="soft" style="font-size:14px">For ${clock12(t.wake)}: your ${dur(t.goal_min)} goal${t.catch_up_min ? `, plus ${t.catch_up_min} minutes to pay back this week's ${dur(t.debt_min)} sleep debt over the next three nights` : ""}.</span>
      ${why1}
    </div>
    <div class="inline" style="gap:24px;font-size:13px;color:#B8AEE0">
      <div class="stat"><span>Wind down from</span><span style="font-size:18px;font-weight:600;color:var(--text)">${clock12(t.wind_down)}</span></div>
      <div class="stat"><span>Wake target</span><span style="font-size:18px;font-weight:600;color:var(--text)">${clock12(t.wake)}</span></div>
    </div>
  </article>`;
}

function tonightFromRange(app, range) {
  const s = app.settings;
  const debt = range.debt_min;
  const catchUp = Math.min(Math.round(debt / 3), 30);
  let m = (toMinutes(s.wake_target) - s.sleep_goal_min - catchUp + 1440) % 1440;
  m = (Math.round(m / 5) * 5) % 1440;
  const f = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
  return { asleep_by: f(m), wind_down: f((m - 30 + 1440) % 1440), wake: s.wake_target, goal_min: s.sleep_goal_min, catch_up_min: catchUp, debt_min: debt };
}

const toMinutes = (hhmm) => { const [a, b] = hhmm.split(":").map(Number); return a * 60 + b; };

// ----------------------------------------------------------- the period

function summaryTiles(app, days, debt) {
  const nights = days.filter((d) => d.night);
  const scores = nights.map((d) => d.night.score);
  const best = nights.reduce((a, d) => (!a || d.night.score > a.night.score ? d : a), null);
  const worst = nights.reduce((a, d) => (!a || d.night.score < a.night.score ? d : a), null);
  const total = mean(days.map((d) => d.sleep_total_min || null));
  const naps = days.reduce((a, d) => a + d.naps.length, 0);
  const beds = nights.map((d) => d.night.bed_from_noon);
  const wakes = nights.map((d) => d.night.wake_from_noon);
  const sd = (v) => { const m = mean(v); return Math.sqrt(mean(v.map((x) => (x - m) ** 2))); };
  const consistency = nights.length >= 3 ? Math.max(0, Math.min(100, Math.round(100 - 0.5 * (sd(beds) + sd(wakes))))) : null;
  const spread = beds.length ? Math.max(...beds) - Math.min(...beds) : null;
  const s = app.settings;
  const scoreWhy = `Best ${best ? dayName(best.date, true) + " " + best.night.score : "–"} · lowest ${worst ? dayName(worst.date, true) + " " + worst.night.score : "–"}`;
  return `<section class="grid small" aria-label="Summary">
    ${tile("Average sleep score", isNum(mean(scores)) ? Math.round(mean(scores)) : "–", nights.length ? h(scoreWhy) : "", C.violet)}
    ${tile("Average sleep", dur(total), `Goal ${dur(s.sleep_goal_min)}${naps ? ` · includes ${naps} nap${naps === 1 ? "" : "s"}` : ""}`)}
    ${tile("Consistency", isNum(consistency) ? `${consistency} <span class="small muted" style="font-weight:400">/ 100</span>` : "–", isNum(spread) ? `Bedtime varied by up to ${Math.round(spread)} min` : "", isNum(consistency) && consistency < 75 ? C.amber : "")}
    ${tile("Average bed / wake", nights.length ? `${clockFromNoon(mean(beds))} <span class="small muted" style="font-weight:400">/ ${clockFromNoon(mean(wakes))}</span>` : "–", `Targets ${clock12(s.bed_target)} / ${clock12(s.wake_target)}`)}
    ${tile("Sleep debt", dur(debt), "Last 7 days, naps included")}
  </section>`;
}

function perNight(app, days) {
  const s = app.settings;
  const long = days.length > 45;
  const items = days.map((d) => {
    const n = d.night;
    const segs = n
      ? [
          { v: (n.deep_min || 0) / 60, color: C.deep },
          { v: (n.light_min || 0) / 60, color: C.light },
          { v: (n.rem_min || 0) / 60, color: C.rem },
          { v: (n.awake_min || 0) / 60, color: C.awake },
        ]
      : [];
    if (n && n.deep_min == null) segs.splice(0, 3, { v: n.asleep_min / 60, color: C.light });
    if (d.nap_min) segs.push({ v: d.nap_min / 60, color: C.nap });
    return {
      key: d.date,
      label: days.length <= 8 ? dayName(d.date, true) : String(Number(d.date.slice(8))),
      current: d.date === selected,
      segs,
      top: !long && n ? n.score : undefined,
      topColor: n && n.score < 60 ? C.amber : C.rem,
    };
  });
  return columns(items, { height: 240, max: 10, goal: s.sleep_goal_min / 60, yTicks: [0, 2, 4, 6, 8, 10], fmtY: (v) => `${v}h`, label: "Sleep per night", clickAction: "night" });
}

function bedWake(app, days) {
  const s = app.settings;
  const lo = 540; // 9pm, as minutes after noon
  const hi = 1380; // 11am
  const W = Math.max(days.length * 60, 100);
  const H = 240;
  const sy = scale(lo, hi, 0, H);
  const bedT = (toMinutes(s.bed_target) - 720 + 1440) % 1440;
  const wakeT = (toMinutes(s.wake_target) - 720 + 1440) % 1440;
  const colW = W / days.length;
  const bw = Math.min(24, colW * 0.4);
  const list = days.filter((d) => d.night).map((d) => {
    const i = days.indexOf(d);
    const x = i * colW + (colW - bw) / 2;
    return [x, x + bw, Math.min(Math.max(d.night.bed_from_noon, lo), hi), Math.min(Math.max(d.night.wake_from_noon, lo), hi)];
  });
  const inner = `<rect x="0" y="${sy(bedT).toFixed(1)}" width="${W}" height="${(sy(wakeT) - sy(bedT)).toFixed(1)}" fill="#22303A"></rect>` + fill(rects(list.map(([a, b, t, u]) => [a, b, t, u]), (v) => v, sy), C.violet);
  const labels = ["9pm", "12am", "3am", "6am", "9am"];
  return `<div style="display:grid;grid-template-columns:44px 1fr;gap:0 10px">
    <div style="display:flex;flex-direction:column;justify-content:space-between;font-size:12px;color:var(--faint);height:262px;text-align:right">${labels.map((l) => `<span>${l}</span>`).join("")}</div>
    ${wide(W, H, inner, { height: 262, label: `Bed and wake times against the ${clock12(s.bed_target)} to ${clock12(s.wake_target)} target window` })}
    <span></span><div class="xlabels" style="grid-template-columns:repeat(${days.length},minmax(0,1fr))">${days.map((d) => `<span>${days.length <= 8 ? dayName(d.date, true) : ""}</span>`).join("")}</div>
  </div>`;
}

// ------------------------------------------------------------ one night

function nightSection(app, data) {
  const night = data.night;
  if (!night) {
    const naps = (data.naps || []).length ? ` Naps: ${data.naps.map((n) => `${clock12(n.bed)}–${clock12(n.wake)} (${dur(n.asleep_min)})`).join(", ")}.` : "";
    return `<section class="card"><h2>${h(nightTitle(data.date))}</h2><p class="empty">No night's sleep recorded.${h(naps)}</p></section>`;
  }
  const det = data.detail;
  const length = det ? det.length_min : Math.round((night.wake_ts - night.bed_ts) / 60);
  const parts = night.score_parts || {};
  const meters = [
    parts.duration && meter("Duration", parts.duration.s, dur(night.asleep_min), C.violet),
    parts.restorative && meter("Deep and REM", parts.restorative.s, `${parts.restorative.percent}% of sleep`, colorFor(parts.restorative.s) === C.teal ? C.violet : C.amber),
    parts.interruptions && meter("Interruptions", parts.interruptions.s, `${isNum(night.awake_spells) ? night.awake_spells + " · " : ""}${dur(night.awake_min)}`, colorFor(parts.interruptions.s) === C.teal ? C.violet : C.amber),
    parts.timing && meter("Timing", parts.timing.s, lateText(parts.timing.late_min), colorFor(parts.timing.s) === C.teal ? C.violet : C.amber),
    parts.heart && meter("Heart rate and stress", parts.heart.s, night.overnight ? `low ${night.overnight.hr_min} · ${Math.round(night.overnight.stress_avg ?? 0)}` : "", colorFor(parts.heart.s) === C.teal ? C.violet : C.amber),
  ].filter(Boolean).join("");
  const scoreWhy = why(app, {
    rule: `Health Hub's own score out of 100: ${Object.entries(parts).map(([k, p]) => `${PART_NAMES[k].toLowerCase()} ${p.weight}%`).join(", ")}. Duration is against your goal; deep and REM against your usual share; interruptions lose points for time awake; timing against your bedtime target; heart rate and stress against your usual nights.`,
    note: night.fitbit_score ? `Fitbit scored this night ${Math.round(night.fitbit_score)}. Fitbit's score is worked out differently, so the two don't match exactly.` : "Parts without enough data are left out and the rest re-weighted.",
  }, { key: "why-sleep-score", label: "How this score works" });
  const ox = data.oxygen;
  const oxygen = ox
    ? `<div class="card soft" style="padding:12px 14px;gap:4px"><span style="font-weight:600;color:${ox.flagged ? "var(--amber)" : "var(--text)"}">${h(ox.title)}</span><span class="small soft">${h(ox.text)}</span>${why(app, ox.why, { key: "why-oxygen" })}</div>`
    : "";
  const chart = det && det.readings.length ? nightCharts(app, night, det, length) : det && det.segments.length ? hypnogramOnly(night, det, length) : `<p class="muted small">${night.source === "imported" ? "This night comes from your Fitbit history: totals only, no stage timeline or readings." : "No readings for this night."}</p>`;
  const naps = (data.naps || []).length ? `<p class="small muted">Naps: ${data.naps.map((n) => `${clock12(n.bed)}–${clock12(n.wake)} (${dur(n.asleep_min)})`).join(", ")}</p>` : "";
  return `<article class="card" aria-label="Selected night" style="gap:18px">
    <div class="head"><h2>${h(nightTitle(data.date))} · ${clock12(night.bed)} to ${clock12(night.wake)}</h2><span class="small muted">${det && det.readings.length ? "Every dot is one reading from the band" : night.source === "imported" ? "From Fitbit history" : ""}</span></div>
    <div class="row" style="gap:28px">
      <div style="flex:999 1 640px;min-width:0">${chart}</div>
      <div style="flex:1 1 280px;min-width:0;display:flex;flex-direction:column;gap:14px">
        <div style="display:flex;align-items:center;gap:16px">
          ${ring((night.score || 0) / 100, { size: 96, color: C.violet, text: String(night.score ?? "–"), textSize: 22, label: `Sleep score ${night.score}` })}
          <div class="stat"><span class="small muted">Sleep score</span><span style="font-size:17px;font-weight:600">${h(night.score_label || "")}</span>${night.fitbit_score ? `<span class="tiny muted">Fitbit: ${Math.round(night.fitbit_score)}</span>` : ""}</div>
        </div>
        <ul class="meters">${meters}</ul>
        ${scoreWhy}
        ${oxygen}
        <dl style="margin:0;display:grid;grid-template-columns:1fr auto auto;gap:8px 14px;font-size:13px">${stageRows(night, data.baseline)}</dl>
        ${naps}
      </div>
    </div>
    ${det && det.readings.length ? rawTable(app, night, det) : ""}
  </article>`;
}

function nightTitle(date) {
  return `${dayName(addDays(date, -1))} night → ${dayName(date)} ${shortDate(date)}`;
}

function hypnogramOnly(night, det, length) {
  return `<div class="lanes"><span class="lab">Stages</span>${hypnogram(det.segments, length, { height: 120 })}<span></span>${axis(nightTimes(night, length))}</div>`;
}

function nightCharts(app, night, det, length) {
  const W = 900;
  const sx = scale(0, length, 0, W);
  const r = det.readings; // [minute, hr, spo2, stress, stage]
  const hr = r.filter((x) => isNum(x[1])).map((x) => [x[0], x[1]]);
  const sp = r.filter((x) => isNum(x[2])).map((x) => [x[0], x[2]]);
  const st = r.filter((x) => isNum(x[3])).map((x) => [x[0], x[3]]);
  const hrLo = Math.min(...hr.map((p) => p[1]), 50) - 2;
  const hrHi = Math.max(...hr.map((p) => p[1]), 80) + 2;
  const syH = scale(hrLo, hrHi, 76, 4);
  const low = lowestHr(r);
  const lowMark = low ? `<path d="M${sx(low.minute).toFixed(1)} ${syH(low.bpm).toFixed(1)} l0.01 0" stroke="#FFFFFF" stroke-width="11" stroke-linecap="round" fill="none" vector-effect="non-scaling-stroke" opacity="0.9"></path><path d="M${sx(low.minute).toFixed(1)} ${syH(low.bpm).toFixed(1)} l0.01 0" stroke="${C.rose}" stroke-width="7" stroke-linecap="round" fill="none" vector-effect="non-scaling-stroke"></path>` : "";
  const hrSvg = wide(W, 80, stroke(line(hr, sx, syH), C.rose, 1, 'stroke-opacity="0.45"') + dotLayer(dots(hr, sx, syH), C.rose, 3.5) + lowMark, { height: 80, label: `Overnight heart rate${low ? `, lowest ${low.bpm} at ${clock12(addMin(night.bed, low.minute))}` : ""}` });
  const spLo = Math.min(86, ...sp.map((p) => p[1])) - 1;
  const syS = scale(spLo, 100, 76, 4);
  const spSvg = wide(W, 80, `<rect x="0" y="${syS(90).toFixed(1)}" width="${W}" height="${(76 - syS(90)).toFixed(1)}" fill="${C.roseBand}"></rect>` + dotLayer(dots(sp, sx, syS), C.blue, 4.5), { height: 80, label: "Overnight blood oxygen; the shaded band is below 90%" });
  const syT = scale(0, 60, 56, 4);
  const stSvg = wide(W, 60, dotLayer(dots(st, sx, syT), C.amber, 4.5), { height: 60, label: "Overnight stress" });
  const range = (pts) => (pts.length ? `${Math.min(...pts.map((p) => p[1]))}–${Math.max(...pts.map((p) => p[1]))}` : "–");
  const tip = (pts, unit) => pts.map(([m, v]) => [m, `${clock12(addMin(night.bed, m))} · ${v}${unit}`]);
  return `<div class="lanes">
    <span class="lab">Stages</span>${det.segments.length ? hypnogram(det.segments, length, { height: 120 }) : `<span class="muted small">No stages</span>`}
    <span class="lab">Heart rate<b>${range(hr)}</b>bpm</span>${hoverable(hrSvg, 0, length, tip(hr, " bpm"))}
    <span class="lab">Blood oxygen<b>${range(sp)}</b>%</span>${hoverable(spSvg, 0, length, tip(sp, "%"))}
    <span class="lab">Stress<b>${st.length ? Math.round(mean(st.map((p) => p[1]))) : "–"}</b>avg</span>${hoverable(stSvg, 0, length, tip(st, ""))}
    <span></span>${axis(nightTimes(night, length))}
  </div>`;
}

function rawTable(app, night, det) {
  const rows = det.readings;
  const csv = ["time,minute,stage,heart_rate,spo2,stress"].concat(rows.map((x) => `${addMin(night.bed, x[0])},${x[0]},${x[4] || ""},${x[1] ?? ""},${x[2] ?? ""},${x[3] ?? ""}`)).join("\n");
  const href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
  const tr = (x) => `<tr><td>${clock12(addMin(night.bed, x[0]))}</td><td>${h(x[4] ? x[4][0].toUpperCase() + x[4].slice(1) : "–")}</td><td>${x[1] ?? "–"}</td><td>${x[2] ?? "–"}</td><td>${x[3] ?? "–"}</td></tr>`;
  const head = `<thead><tr><th>Time</th><th>Stage</th><th>Heart rate</th><th>Blood oxygen</th><th>Stress</th></tr></thead>`;
  return `<div style="border-top:1px solid var(--line);padding-top:16px;display:flex;flex-direction:column;gap:10px">
    <div class="head"><h3 style="font-size:14px;font-weight:600;color:var(--soft)">Raw readings <span class="muted" style="font-weight:400">· ${rows.length} minutes with a reading</span></h3>
      <a href="${href}" download="sleep-${h(night.bed_ts)}.csv" class="small">Download CSV</a></div>
    <details class="why" data-k="raw-${night.bed_ts}"><summary>Show all readings</summary>
      <div class="scroll" style="max-height:420px;overflow-y:auto"><table style="min-width:560px">${head}<tbody>${rows.map(tr).join("")}</tbody></table></div>
    </details>
  </div>`;
}

// ------------------------------------------------------------ long view

function longTerm(app, history) {
  const have = history.months || [];
  if (have.length < 3) return "";
  // One slot per calendar month, so gaps without a tracker show as gaps.
  const byKey = Object.fromEntries(have.map((m) => [m.month, m]));
  const months = [];
  let [y, mo] = have[0].month.split("-").map(Number);
  const last = have[have.length - 1].month;
  for (;;) {
    const key = `${y}-${String(mo).padStart(2, "0")}`;
    months.push(byKey[key] || { month: key, hours: null, nights: 0, fitbit_score: null, hub_score: null });
    if (key === last) break;
    mo += 1;
    if (mo > 12) { mo = 1; y += 1; }
  }
  const W = 600;
  const n = months.length;
  const sx = scale(0, n - 1, 0, W);
  const hours = months.map((m, i) => [i, m.hours]);
  const hv = hours.map((p) => p[1]).filter(isNum);
  const lo = Math.floor(Math.min(...hv) * 2) / 2 - 0.25;
  const hi = Math.ceil(Math.max(...hv) * 2) / 2 + 0.25;
  const sy = scale(lo, hi, 120, 0);
  const nb = history.normal_range;
  const bandSvg = nb ? `<rect x="0" y="${sy(nb[1]).toFixed(1)}" width="${W}" height="${(sy(nb[0]) - sy(nb[1])).toFixed(1)}" fill="#2A2440"></rect>` : "";
  const hoursSvg = wide(W, 120, bandSvg + stroke(line(hours, sx, sy), C.violet, 2), { height: 120, label: "Average sleep by month" });
  const scoreF = months.map((m, i) => [i, m.fitbit_score]);
  const scoreH = months.map((m, i) => [i, m.hub_score]);
  const sv = scoreF.concat(scoreH).map((p) => p[1]).filter(isNum);
  const syS = scale(Math.min(60, ...sv), Math.max(95, ...sv), 120, 0);
  const scoreSvg = wide(W, 120, stroke(line(scoreF, sx, syS), C.faint, 2) + stroke(line(scoreH, sx, syS), C.violet, 2.5) + dotLayer(dots(scoreH, sx, syS), C.violet, 6), { height: 120, label: "Sleep score by month: Fitbit's, then Health Hub's" });
  const years = [...new Set(months.map((m) => m.month.slice(0, 4)))];
  const gaps = findGaps(have);
  const tipH = months.map((m, i) => [i, `${monthLabel(m.month)} · ${isNum(m.hours) ? `${dur(m.hours * 60)} (${m.nights} nights)` : "no data"}`]);
  const tipS = months.map((m, i) => [i, `${monthLabel(m.month)} · ${isNum(m.fitbit_score) ? `Fitbit ${Math.round(m.fitbit_score)}` : ""}${isNum(m.hub_score) ? ` Health Hub ${Math.round(m.hub_score)}` : ""}` || "no data"]);
  return `<section class="grid" aria-label="Long-term" style="grid-template-columns:repeat(auto-fit,minmax(380px,1fr))">
    <article class="card"><div class="head"><h2>Average sleep by month</h2><span class="tiny muted">since ${h(monthLabel(have[0].month))}</span></div>
      ${hoverable(hoursSvg, 0, n - 1, tipH)}${axis(years)}
      <p class="small muted">${nb ? `Shaded: your normal range, ${dur(nb[0] * 60)} to ${dur(nb[1] * 60)} (the middle 80% of months).` : ""}${gaps ? ` Gaps: ${h(gaps)}.` : ""}</p></article>
    <article class="card"><div class="head"><h2>Sleep score</h2>${legend([[C.faint, "Fitbit"], [C.violet, "Health Hub"]])}</div>
      ${hoverable(scoreSvg, 0, n - 1, tipS)}${axis(years)}
      <p class="small muted">The two scores are worked out differently, so compare trends within each rather than across the join.</p></article>
  </section>`;
}

function monthLabel(key) {
  const [y, m] = key.split("-").map(Number);
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1]} ${y}`;
}

function findGaps(months) {
  const out = [];
  for (let i = 1; i < months.length; i++) {
    const [y0, m0] = months[i - 1].month.split("-").map(Number);
    const [y1, m1] = months[i].month.split("-").map(Number);
    const diff = (y1 - y0) * 12 + (m1 - m0);
    if (diff > 2) out.push(`${monthLabel(months[i - 1].month)} to ${monthLabel(months[i].month)}`);
  }
  return out.join("; ");
}
