// Longevity: a report card of long-term habits against published guidance.
// A summary, not another detail page: each area links to the page with the detail.

import { C, dotLayer, dots, hline, hoverable, line, scale, stroke, wide } from "../charts.js";
import { dur, h, isNum, monthName, num, shortDate } from "../util.js";
import { loadReview, reviewActions, reviewCard, sourceLinks, why } from "../parts.js";

export const usesPeriod = false;
export const title = () => "Your habits and measurements against the long-term guidance";

const RATING = {
  good: ["On track", "lv-good"],
  fair: ["Fair", "lv-fair"],
  low: ["Needs attention", "lv-low"],
};
const PAGE_NAMES = { heart: "Heart", activity: "Activity & load", sleep: "Sleep", body: "Body" };

export async function load(app) {
  const [report, review] = await Promise.all([app.get({ type: "health_hub/longevity" }), loadReview(app, "longevity")]);
  report.review = review;
  return report;
}

function pill(rating) {
  if (!rating) return `<span class="lv-pill lv-none">Not rated yet</span>`;
  const [label, cls] = RATING[rating];
  return `<span class="lv-pill ${cls}">${label}</span>`;
}

function fmt(m, v) {
  if (!isNum(v)) return "–";
  if (m.display && v === m.value) return m.display;
  if (m.format === "duration") return dur(v);
  if (isNum(m.decimals)) return num(v, Number.isInteger(v) ? 0 : m.decimals);
  return num(v, Number.isInteger(v) ? 0 : 1);
}

function fmtChange(m, v) {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "±";
  const a = Math.abs(v);
  if (m.format === "duration") return `${sign}${Math.round(a)} min`;
  if (m.unit === "bpm") return `${sign}${num(a, 1)} bpm`;
  if (m.unit === "days a week") return `${sign}${num(a, 1)} a week`;
  return `${sign}${num(a, a < 10 && !Number.isInteger(a) ? 1 : 0)}`;
}

function trendLine(m) {
  const t = m.trend;
  const vs = m.trend_label || "vs the 3 months before";
  if (!t) return `<span class="tiny faint">No earlier figure to compare with yet</span>`;
  if (t.direction === "steady") return `<span class="small muted">About the same ${vs.replace(/^vs /, "as ")}</span>`;
  const up = t.change > 0;
  const color = t.direction === "better" ? "var(--teal)" : "var(--amber)";
  return `<span class="small" style="color:${color}">${up ? "▲" : "▼"} ${h(fmtChange(m, t.change))} ${h(vs)}</span>`;
}

function spark(m) {
  const pts = m.monthly.map(([, v], i) => [i, v]);
  const vals = pts.map((p) => p[1]).filter(isNum);
  if (vals.length < 2) return `<p class="tiny faint lv-nospark">The monthly trend appears once there are two months of figures.</p>`;
  const goal = isNum(m.goal) ? m.goal : m.key === "resting_hr" ? 60 : null;
  const all = vals.concat(isNum(goal) ? [goal] : []);
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.15;
  lo -= pad;
  hi += pad;
  const W = 360;
  const H = 64;
  const sx = scale(0, pts.length - 1, 5, W - 5);
  const sy = scale(lo, hi, H - 5, 5);
  const inner =
    (isNum(goal) ? hline(sy(goal), W, C.dim, "4 4") : "") +
    stroke(line(pts, sx, sy), C.blue, 2) +
    dotLayer(dots(pts, sx, sy), C.blue, 5);
  const label = (key) => {
    const [y, mo] = key.split("-").map(Number);
    return `${monthName(mo - 1)} ${String(y).slice(2)}`;
  };
  const tips = m.monthly.map(([k, v], i) => [i, `${label(k)} · ${isNum(v) ? fmt(m, v) + (m.format === "duration" ? "" : " " + m.unit) : "no figure"}`]);
  return `<div class="lv-spark">
      ${hoverable(wide(W, H, inner, { height: H, label: `${m.label} by month over the last 12 months` }), 0, pts.length - 1, tips)}
      <div class="axis"><span>${h(label(m.monthly[0][0]))}</span><span>${isNum(goal) ? "dashed: guidance" : ""}</span><span>${h(label(m.monthly[m.monthly.length - 1][0]))}</span></div>
    </div>`;
}

// Lower-case the first word unless it's an abbreviation (HbA1c, LDL).
const lower = (s) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);

function metric(app, m) {
  const unit = m.format === "duration" ? "" : m.unit;
  return `<div class="lv-metric">
      <div class="lv-main">
        <h3>${h(m.label)}</h3>
        <div><span class="big">${h(fmt(m, m.value))}</span>${isNum(m.value) && unit ? ` <span class="small muted">${h(unit)}</span>` : ""}</div>
        <p class="tiny faint">${h(m.summary)}</p>
      </div>
      <div class="lv-judge">
        ${pill(m.rating)}
        <span class="small soft">Guidance: ${h(m.target)}${sourceLinks(app, m.sources)}</span>
        ${trendLine(m)}
      </div>
      ${spark(m)}
    </div>
    ${why(app, { rule: m.rule, note: m.note, sources: m.why_sources || [] }, { key: `why-lv-${m.key}`, label: `How ${lower(m.label.replace(/\s*\(.*\)/, ""))} is rated` })}`;
}

const mmss = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;

function fitnessAge(fa) {
  if (!fa || !isNum(fa.age)) return "–";
  return `${fa.bound === "under" ? "under " : fa.bound === "over" ? "over " : ""}${fa.age}`;
}

function walkTest(app, data) {
  const ready = data.walk_test_ready;
  const missing = [
    !ready.sex && `<a href="/health/settings" data-action="page" data-arg="settings">your sex</a>`,
    !ready.age && `<a href="/health/settings" data-action="page" data-arg="settings">your age</a>`,
    !ready.weight && `<a href="/health/body" data-action="page" data-arg="body">a weigh-in from the last 90 days</a>`,
  ].filter(Boolean);
  const tests = data.walk_tests;
  const now = new Date();
  const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  return `<details class="why lv-test" data-k="lv-walktest" ${tests.length ? "" : "open"}>
      <summary>${tests.length ? "Do another walk test" : "Do the 1-mile walk test"}</summary>
      <div class="lv-test-body">
        <ol class="small soft lv-steps">
          <li>Find a flat, measured mile (1.61 km): four laps of a 400 m running track and 9 m more, or a route you've measured on a map.</li>
          <li>Wear the band. Warm up with 5–10 minutes of easy walking.</li>
          <li>Walk the mile as fast as you can without running, at an even pace.</li>
          <li>Note how long it took and the clock time you finished. If you can read your heart rate as you cross the line, note that too; otherwise the band's reading from that minute is used.</li>
          <li class="faint">If you have a heart condition or haven't exercised in a while, check with your doctor first.</li>
        </ol>
        ${missing.length ? `<p class="small soft">Before the test can be scored, add ${missing.join(", ")}. Your weight comes from the Body page, so there's nothing to enter twice.</p>` : ""}
        <form class="settings lv-form" data-submit="walk">
          <label>Date<input name="date" type="date" value="${h(app.today)}" max="${h(app.today)}" required></label>
          <label>Finished at<input name="finish" type="time" value="${h(hhmm)}" required></label>
          <label>Time taken<span class="inline"><input name="minutes" type="number" min="5" max="60" required style="width:80px" aria-label="Minutes" placeholder="min"> : <input name="seconds" type="number" min="0" max="59" style="width:80px" aria-label="Seconds" placeholder="sec"></span></label>
          <label>Heart rate at the finish (optional)<input name="hr" type="number" min="60" max="230" placeholder="from the band"></label>
          <button class="btn" type="submit">Save walk test</button>
        </form>
      </div>
    </details>
    ${tests.length ? `<div class="scroll"><table><thead><tr><th>Date</th><th>Time</th><th>Finish heart rate</th><th>Weight</th><th>VO2max</th><th>Fitness age</th><th></th></tr></thead><tbody>${tests
      .map((t) => `<tr><td>${h(shortDate(t.date, true))}</td><td>${mmss(t.seconds)}</td><td>${t.hr} bpm <span class="faint">(${t.hr_from === "band" ? "band" : "you"})</span></td><td>${isNum(t.weight_kg) ? `${num(t.weight_kg, 1)} kg` : "–"}</td><td>${isNum(t.vo2max) ? num(t.vo2max, 1) : "–"}</td><td>${h(fitnessAge(t.fitness_age))}</td><td><button class="btn" style="min-height:32px" data-action="delwalk" data-arg="${t.ts}">Delete</button></td></tr>`)
      .join("")}</tbody></table></div>` : ""}`;
}

function partly(a) {
  const rated = a.metrics.filter((m) => m.rating).length;
  return a.rating && rated < a.metrics.length ? `<span class="tiny faint">${rated} of ${a.metrics.length} rated</span>` : "";
}

function area(app, a, data) {
  return `<article class="card lv-area">
      <div class="head">
        <div class="inline"><h2 class="lv-title">${h(a.title)}</h2>${pill(a.rating)}${partly(a)}</div>
        ${a.page ? `<a href="/health/${a.page}" data-action="page" data-arg="${a.page}" class="small">${h(PAGE_NAMES[a.page] || a.title)} page ›</a>` : ""}
      </div>
      ${a.action ? `<p class="lv-action"><span aria-hidden="true">→</span> ${h(a.action)}</p>` : ""}
      ${a.metrics.map((m) => metric(app, m)).join("")}
      ${a.walk_test ? walkTest(app, data) : ""}
    </article>`;
}

export function render(app, data) {
  const c = data.counts;
  const unrated = data.total - data.rated;
  const parts = [
    c.good && `<b style="color:var(--teal)">${c.good} on track</b>`,
    c.fair && `<b style="color:var(--amber)">${c.fair} fair</b>`,
    c.low && `<b style="color:var(--rose)">${c.low} need${c.low === 1 ? "s" : ""} attention</b>`,
    unrated && `<span class="muted">${unrated} not rated yet</span>`,
  ].filter(Boolean);
  return `<div class="lv-areas"><section class="card lv-intro">
      <div class="head"><h2>How your habits compare with the long-term guidance</h2><span class="small">${parts.join(" · ")}</span></div>
      <p class="small soft">Up to ${h(shortDate(data.as_of, true))}. Habits (heart, movement, sleep) cover the last 3 months; measurements (fitness, body, blood tests) show your latest entry. Each is rated against published guidance or large studies of how they relate to long-term health, and the line shows the last 12 months. These describe habits across populations, not a diagnosis. The day-to-day detail stays on each area's own page.</p>
    </section>
    ${data.review ? reviewCard(app, data.review, { kind: "longevity" }) : ""}
    ${data.areas.map((a) => area(app, a, data)).join("")}</div>`;
}

export const actions = {
  ...reviewActions,
  walk: async (app, data) => {
    const msg = { type: "health_hub/walk_test/log", date: data.date, finish: data.finish, minutes: Number(data.minutes), seconds: Number(data.seconds || 0) };
    if (data.hr !== "") msg.hr = Number(data.hr);
    await app.call(msg);
    app.toast("Walk test saved.");
    await app.render(true);
  },
  delwalk: async (app, arg) => {
    await app.call({ type: "health_hub/walk_test/delete", ts: Number(arg) });
    app.toast("Walk test deleted.");
    await app.render(true);
  },
};
