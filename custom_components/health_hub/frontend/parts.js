// Pieces several pages share: "Why?" boxes, highlights, the daily review,
// training and rewards, and small figure blocks.

import { C, ring } from "./charts.js";
import { clock12, dur, h, isNum, num, shortDate } from "./util.js";

let uid = 0;

/** A "Why?" disclosure. key keeps it open across refreshes. */
export function why(app, { rule, numbers, note, sources = [] } = {}, { key, label = "Why?", center = false, open = false } = {}) {
  const k = key || `why${uid++}`;
  const src = sourceLinks(app, sources);
  return `<details class="why${center ? " c" : ""}" data-k="${h(k)}" ${open ? "open" : ""}>
    <summary>${h(label)}</summary>
    <div class="box">
      ${rule ? `<span>${h(rule)}</span>` : ""}
      ${numbers ? `<span class="muted">${h(numbers)}</span>` : ""}
      ${note ? `<span>${h(note)}</span>` : ""}
      ${src}
    </div>
  </details>`;
}

export function sourceLinks(app, keys) {
  return (keys || [])
    .map((k) => app.sources[k])
    .filter(Boolean)
    .map((s) => `<a class="tiny" href="${h(s.url)}" target="_blank" rel="noopener noreferrer">${h(s.title)} (${h(s.publisher)}${s.year ? ", " + h(s.year) : ""}) ↗</a>`)
    .join("");
}

const ICONS = {
  "trend-up": '<path d="M3 17l6-6 4 4 8-8"></path><path d="M15 7h6v6"></path>',
  "trend-down": '<path d="M3 7l6 6 4-4 8 8"></path><path d="M15 17h6v-6"></path>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path>',
  clock: '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 3"></path>',
  trophy: '<path d="M8 21h8"></path><path d="M12 17v4"></path><path d="M7 4h10v5a5 5 0 0 1-10 0z"></path><path d="M17 5h3v2a3 3 0 0 1-3 3"></path><path d="M7 5H4v2a3 3 0 0 0 3 3"></path>',
};

export function icon(name, color = C.teal, size = 22) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.clock}</svg>`;
}

const TONE = { good: C.teal, watch: C.amber, info: C.blue };

export function highlights(app, list, empty = "Nothing stands out yet. Highlights appear once there are a couple of weeks of band data to compare.") {
  if (!list || !list.length) return `<section class="card soft"><p class="muted small">${h(empty)}</p></section>`;
  return `<section class="grid" aria-label="Highlights">${list
    .map(
      (it) => `<article class="card soft" style="flex-direction:row;gap:14px;align-items:flex-start">
        ${icon(it.icon, TONE[it.tone] || C.blue)}
        <div style="display:flex;flex-direction:column;min-width:0">
          <p class="small soft" style="font-size:14px"><strong style="color:var(--text);font-weight:600">${h(it.title)}</strong> ${h(it.text)}</p>
          ${why(app, it.why, { key: `hl-${it.id}` })}
        </div>
      </article>`,
    )
    .join("")}</section>`;
}

// ----------------------------------------------------------------- review

const LEVEL = { good: "Good", neutral: "For information", watch: "Worth watching", see_doctor: "Talk to a doctor" };

function reviewLinks(sources) {
  return (sources || [])
    .map((s) => `<a class="tiny" href="${h(s.url)}" target="_blank" rel="noopener noreferrer">${h(s.title)}${s.publisher ? ` (${h(s.publisher)}${s.year ? ", " + h(s.year) : ""})` : ""} ↗</a>`)
    .join("");
}

export function reviewCard(app, data, { topics = null, compact = false } = {}) {
  const latest = data && data.latest;
  const reviewer = (data && data.reviewer) || {};
  const attempt = data && data.last_attempt;
  const enabled = data ? data.enabled : false;
  const pending = attempt && attempt.status === "pending";
  const stateText = {
    ready: "", running: "Claude is writing a review…", no_login: "The Reviewer add-on isn't signed in to Claude.",
    offline: "The Reviewer add-on isn't running.", not_installed: "Install the Health Hub Reviewer add-on to get a daily review.",
    error: "The last review didn't work.", disabled: "The daily review is turned off in Health Hub's options.", unknown: "",
  }[reviewer.state] || "";
  const button = enabled ? `<button class="btn" data-action="review" ${pending ? "disabled" : ""}>${pending ? "Writing…" : "Review again"}</button>` : "";
  if (!latest || !latest.review) {
    const msg = pending ? "Claude is writing today's review…" : attempt && attempt.status === "error" ? `The last review didn't work: ${attempt.error || "no answer"}` : stateText || "No review yet. One is written each morning once last night's sleep has synced.";
    return `<section class="card" aria-label="Daily review"><div class="head"><h2>Daily review</h2>${button}</div><p class="muted small">${h(msg)}</p></section>`;
  }
  const r = latest.review;
  const when = latest.finished ? new Date(latest.finished) : null;
  const time = when ? when.toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit", timeZone: app.info.time_zone }).replace(" ", "").toLowerCase() : "";
  const nSources = new Set([...(r.observations || []), ...(r.suggestions || [])].flatMap((o) => (o.sources || []).map((s) => s.url))).size;
  const isToday = latest.day === app.today;
  let obs = r.observations || [];
  if (topics) obs = obs.filter((o) => topics.includes(o.topic));
  const head = `<div class="head"><div style="display:flex;flex-direction:column;gap:4px">
      <h2>${compact ? "From today's review" : "Daily review"}</h2>
      <span class="small muted">Written ${isToday ? time : `${shortDate(latest.day)} ${time}`} by Claude${nSources ? ` · ${nSources} source${nSources === 1 ? "" : "s"}` : ""}${!isToday ? " · not yet updated today" : ""}</span>
    </div>${compact ? `<a href="/health/" data-action="page" data-arg="overview" class="small" style="min-height:44px;display:inline-flex;align-items:center">Full review on Overview ›</a>` : `<div class="inline">${button}</div>`}</div>`;
  const obsHtml = obs.length
    ? `<ul class="obs">${obs
        .map(
          (o) => `<li><span class="pill ${h(o.level)}">${h(LEVEL[o.level] || o.level)}</span>
            <span style="font-size:15px;font-weight:600">${h(o.title)}</span>
            <span class="small soft">${h(o.detail)}</span>
            ${o.based_on ? `<span class="tiny muted">${h(o.based_on)}</span>` : ""}
            ${reviewLinks(o.sources)}</li>`,
        )
        .join("")}</ul>`
    : compact ? `<p class="muted small">Nothing about this in today's review.</p>` : "";
  if (compact) return `<section class="card" aria-label="From today's review">${head}${obsHtml}</section>`;
  const sugg = (r.suggestions || []).length
    ? `<div style="display:flex;flex-direction:column;gap:10px"><h3>For today</h3><ul style="margin:0;padding-left:20px;display:flex;flex-direction:column;gap:8px;font-size:14px;line-height:1.5">${r.suggestions
        .map((s) => `<li>${h(s.text)} ${s.why ? `<span class="muted">${h(s.why)}</span>` : ""} ${reviewLinks(s.sources)}</li>`)
        .join("")}</ul></div>`
    : "";
  const caveats = (r.caveats || []).length ? `<ul class="tiny faint" style="margin:0;padding-left:18px">${r.caveats.map((c) => `<li>${h(c)}</li>`).join("")}</ul>` : "";
  const sent = latest.summary ? `<details class="why" data-k="review-sent"><summary>See what was sent</summary><div class="box"><pre style="white-space:pre-wrap;margin:0;font-size:12px;color:var(--soft)">${h(JSON.stringify(latest.summary, null, 2))}</pre></div></details>` : "";
  return `<section class="card" aria-label="Daily review" style="gap:18px">
    ${head}
    <div style="display:flex;flex-direction:column;gap:8px;max-width:900px">
      <p class="headline">${h(r.headline)}</p>
      ${r.summary ? `<p style="font-size:15px;line-height:1.6" class="soft">${h(r.summary)}</p>` : ""}
    </div>
    ${obsHtml}${sugg}
    <div style="border-top:1px solid var(--line);padding-top:14px;display:flex;flex-direction:column;gap:6px">
      ${caveats}
      <p class="tiny faint">Claude saw only a summary of your figures, not minute readings or anything that identifies you. This is not medical advice; if something worries you, talk to your doctor.</p>
      ${sent}
    </div>
  </section>`;
}

export async function loadReview(app) {
  try {
    return await app.get({ type: "health_hub/review" });
  } catch (e) {
    return null;
  }
}

export const reviewActions = {
  review: async (app) => {
    await app.callService("health_hub", "request_review");
    app.toast("Asked Claude for a fresh review. It takes about a minute.");
    setTimeout(() => { app.cache.clear(); app.render(true); }, 70000);
    app.render(true);
  },
};

// --------------------------------------------------------------- training

function blocksBar(count, target, color) {
  const n = Math.max(target, count);
  const cells = Array.from({ length: n }, (_, i) => `<span style="background:${i < count ? color : "var(--track)"}"></span>`).join("");
  return `<div class="blocks" style="grid-template-columns:repeat(${n},minmax(0,1fr))" role="img" aria-label="${count} of ${target}">${cells}</div>`;
}

const STATUS_COLOR = { done: C.teal, on_track: C.teal, behind: C.amber };

export function trainingSection(app, t, { full = false } = {}) {
  const day = t.day;
  const label = day === app.today ? "today" : shortDate(day);
  const chips = t.day_logs.length
    ? t.day_logs
        .map((x) => `<span class="chip ${x.kind}">${h(x.kind === "gym" ? cap(x.variant) : "Compex")} · ${h(timeOf(app, x.ts))}<button data-action="undo" data-arg="${x.id}" aria-label="Undo ${h(x.kind === "gym" ? x.variant : "Compex")}">×</button></span>`)
        .join("")
    : `<span class="small muted">Nothing logged ${day === app.today ? "today" : "on this day"} yet.</span>`;
  const b = t.block;
  const weeks = t.weeks
    .map((w, i) => `<div class="${w.current ? "now" : ""} ${w.future ? "future" : ""}">Week ${i + 1}${w.current ? " (now)" : ""}<b style="${w.future ? "color:var(--dim);font-weight:400" : ""}">${w.future ? "–" : `${w.gym} gym · ${w.compex} Compex`}</b></div>`)
    .join("");
  const rw = t.rewards;
  const last = rw.last_earned ? `last earned ${shortDate(rw.last_earned.block_last || app.today)} (${rw.last_earned.delta === 3 ? "both, ×3" : "×1"})` : "none earned yet";
  return `<section class="card" aria-label="Training and rewards" style="gap:20px">
    <div class="head"><h2>Training and rewards</h2><span class="small muted">This block: ${h(shortDate(b.first))} – ${h(shortDate(b.last))} · week ${b.week} of ${b.weeks}${b.is_current ? ` · ${b.days_left} days left, today included` : b.before_first ? " · before your first block, so no rewards" : b.ended ? " · ended" : ""}</span></div>
    <div class="row" style="gap:24px">
      <div style="flex:1 1 300px;min-width:0;display:flex;flex-direction:column;gap:12px">
        <h3>Log for ${h(label)}</h3>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px">
          ${["push", "pull", "legs"].map((v) => `<button class="btn big" data-action="log" data-arg="gym|${v}">${cap(v)}</button>`).join("")}
        </div>
        <button class="btn big" data-action="log" data-arg="compex|">Compex</button>
        <div class="inline">${chips}</div>
        <p class="tiny faint">Logs go on the day you're viewing; use ‹ to log a session you forgot.</p>
      </div>
      <div style="flex:2 1 420px;min-width:0;display:flex;flex-direction:column;gap:18px">
        ${progressRow("Gym", t.gym, C.violet, `This block: ${t.gym.by_variant.push} Push · ${t.gym.by_variant.pull} Pull · ${t.gym.by_variant.legs} Legs`)}
        ${progressRow("Compex", t.compex, C.teal)}
        <div class="weeks">${weeks}</div>
        <p class="small soft">When the block ends on ${h(longDay(b.last))}: both targets hit earns <strong style="color:var(--gold)">3 rewards</strong>, one of them earns 1. The next block starts the day after.</p>
      </div>
      <div class="reward" style="flex:1 1 240px;min-width:0">
        ${icon("trophy", C.gold, 40)}
        <span class="small muted">Rewards to spend</span>
        <span style="font-size:52px;font-weight:700;color:var(--gold);line-height:1">${rw.balance}</span>
        <button class="btn gold" data-action="spend" ${rw.balance > 0 ? "" : "disabled"}>Spend one</button>
        <span class="tiny faint">Earned ${rw.earned} · spent ${rw.spent} · ${h(last)}</span>
      </div>
    </div>
    ${full ? "" : ""}
  </section>`;
}

function progressRow(name, p, color, extra = "") {
  return `<div style="display:flex;flex-direction:column;gap:8px">
    <div class="head"><span style="font-size:14px;font-weight:600">${name} <span class="muted" style="font-weight:400">· ${p.count} of ${p.target} this block</span></span>
    <span class="small" style="color:${STATUS_COLOR[p.status] || C.muted}">${h(p.text)} · ${h(p.detail)}</span></div>
    ${blocksBar(p.count, p.target, color)}
    ${extra ? `<span class="tiny faint">${h(extra)}</span>` : ""}
  </div>`;
}

export const trainingActions = {
  log: async (app, arg) => {
    const [kind, variant] = arg.split("|");
    const msg = { type: "health_hub/training/log", date: app.state.date, kind };
    if (variant) msg.variant = variant;
    await app.call(msg);
    app.toast(`Logged ${kind === "gym" ? cap(variant) : "Compex"} for ${app.state.date === app.today ? "today" : shortDate(app.state.date)}.`);
    await app.render(true);
  },
  undo: async (app, arg) => {
    await app.call({ type: "health_hub/training/undo", log_id: Number(arg), date: app.state.date });
    app.toast("Removed.");
    await app.render(true);
  },
  spend: async (app) => {
    await app.call({ type: "health_hub/rewards/spend", date: app.state.date });
    app.toast("One reward spent. Enjoy it.");
    await app.render(true);
  },
};

// ------------------------------------------------------------------ misc

export const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

export function timeOf(app, ts) {
  return new Date(ts * 1000).toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit", timeZone: app.info.time_zone }).replace(" ", "").toLowerCase();
}

function longDay(s) {
  const d = new Date(`${s}T00:00:00Z`);
  return `${["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][d.getUTCDay()]} ${shortDate(s)}`;
}

export function scoreColor(score) {
  if (!isNum(score)) return C.dim;
  return score >= 70 ? C.teal : score >= 50 ? C.amber : C.rose;
}

export function stat(k, v) {
  return `<div class="stat"><span class="k">${h(k)}</span><span class="v">${v}</span></div>`;
}

export function tile(title, value, sub = "", color = "") {
  return `<article class="card tight"><span class="small muted">${h(title)}</span><span class="big" ${color ? `style="color:${color}"` : ""}>${value}</span>${sub ? `<span class="small soft">${sub}</span>` : ""}</article>`;
}

export function noData(text) {
  return `<section class="card"><p class="empty">${h(text)}</p></section>`;
}

export function stepsRing(steps) {
  const frac = steps.goal ? steps.total / steps.goal : 0;
  return ring(frac, { text: `${Math.round(frac * 100)}%`, label: `Steps ${num(steps.total)} of ${num(steps.goal)}` });
}

export { clock12, dur };
