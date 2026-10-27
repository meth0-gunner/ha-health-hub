// Training: log sessions, the current block with a calendar, rewards and their history.

import { addDays, dayName, h, parseDate, shortDate } from "../util.js";
import { cap, timeOf, trainingActions, trainingSection } from "../parts.js";

export const dayOnly = true;

export async function load(app) {
  return { t: await app.get({ type: "health_hub/training", date: app.state.date }) };
}

export function render(app, data) {
  const t = data.t;
  const b = t.block;
  const byDay = {};
  for (const x of t.calendar) (byDay[x.day] ||= []).push(x);
  const cells = [];
  for (let i = 0; i < b.weeks * 7; i++) {
    const day = addDays(b.first, i);
    const logs = byDay[day] || [];
    const cls = [day === app.today ? "today" : "", day > app.today ? "future" : ""].join(" ");
    cells.push(`<div class="${cls}"><span class="d">${i < 7 ? dayName(day, true) + " " : ""}${parseDate(day).getUTCDate()}</span>${logs
      .map((x) => `<span class="${x.kind === "gym" ? "g" : "c"}" title="${h(timeOf(app, x.ts))}">${h(x.kind === "gym" ? cap(x.variant) : "Compex")}</span>`)
      .join("")}</div>`);
  }
  const ledger = t.rewards.ledger;
  return `${trainingSection(app, t, { full: true })}
    <article class="card">
      <div class="head"><h2>This block, day by day</h2>
        <div class="inline"><button class="btn" data-action="block" data-arg="${h(addDays(b.first, -1))}">‹ Previous block</button>${b.last < app.today ? `<button class="btn" data-action="block" data-arg="${h(addDays(b.last, 1) > app.today ? app.today : addDays(b.last, 1))}">Next block ›</button>` : ""}</div></div>
      <div class="cal" role="grid" aria-label="Sessions per day in this block">${cells.join("")}</div>
      <p class="tiny faint">Click ‹ at the top to step back a day and log a session you forgot; logs always go on the day you're viewing.</p>
    </article>
    <section class="grid">
      <article class="card"><h2>Past blocks</h2>
        ${t.past_blocks.length ? `<table><thead><tr><th>Block</th><th>Result</th><th>Rewards</th></tr></thead><tbody>${t.past_blocks
          .map((p) => `<tr><td>${h(shortDate(p.first))} – ${h(shortDate(p.last))}</td><td class="soft">${h(p.reason.replace(/^block [\d-]+: /, ""))}</td><td>${p.earned ? `+${p.earned}` : "0"}</td></tr>`)
          .join("")}</tbody></table>` : `<p class="empty">No finished blocks yet. Rewards are counted when a block ends.</p>`}</article>
      <article class="card"><h2>Rewards history</h2>
        ${ledger.length ? `<table><thead><tr><th>When</th><th>What</th><th></th></tr></thead><tbody>${ledger
          .map((r) => `<tr><td>${h(new Date(r.ts * 1000).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric", timeZone: app.info.time_zone }))}</td><td class="soft">${r.delta < 0 ? "Spent one" : r.delta ? `Earned for the block from ${h(shortDate(r.block))}` : `No reward for the block from ${h(shortDate(r.block))}`}</td><td style="color:${r.delta < 0 ? "var(--amber)" : "var(--gold)"}">${r.delta > 0 ? "+" : ""}${r.delta}</td></tr>`)
          .join("")}</tbody></table>` : `<p class="empty">Nothing earned or spent yet.</p>`}</article>
    </section>
    <p class="small muted">Targets: gym ${t.targets.gym_per_week} a week (${t.targets.gym} a block), Compex ${t.targets.compex_per_week} a week (${t.targets.compex} a block). Change them in <a href="/health/settings" data-action="page" data-arg="settings">Settings</a>.</p>`;
}

export const actions = {
  ...trainingActions,
  block: async (app, arg) => {
    app.navigate({ date: arg });
  },
};
