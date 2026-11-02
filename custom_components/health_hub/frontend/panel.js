// Health Hub's Health page: a Home Assistant sidebar panel (admin only).
// Plain JavaScript, no libraries; every chart is hand-drawn SVG.

import { CSS } from "./style.js";
import { addDays, daysBetween, h, longDate, periodRange, rangeLabel, relTime } from "./util.js";
import * as overview from "./pages/overview.js";
import * as sleep from "./pages/sleep.js";
import * as readiness from "./pages/readiness.js";
import * as activity from "./pages/activity.js";
import * as heart from "./pages/heart.js";
import * as stress from "./pages/stress.js";
import * as body from "./pages/body.js";
import * as training from "./pages/training.js";
import * as settings from "./pages/settings.js";

const PAGES = [
  ["overview", "Overview", overview],
  ["sleep", "Sleep", sleep],
  ["readiness", "Readiness", readiness],
  ["activity", "Activity & load", activity],
  ["heart", "Heart", heart],
  ["stress", "Stress & energy", stress],
  ["body", "Body", body],
  ["training", "Training", training],
  ["settings", "Settings", settings],
];
const BY_KEY = Object.fromEntries(PAGES.map(([k, , m]) => [k, m]));
const PERIODS = [["day", "Day"], ["week", "Week"], ["month", "Month"], ["year", "Year"], ["custom", "Custom…"]];
const STEP = { day: 1, week: 7, month: 30, year: 365 };
const BASE = "/health";
// The version these files came with: they're served from /health_hub_static/<version>/.
const FILES_VERSION = (new URL(import.meta.url).pathname.match(/\/health_hub_static\/([^/]+)\//) || [])[1] || null;

class HealthHubPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.state = { page: "overview", period: "day", date: null, custom: null };
    this.cache = new Map();
    this.info = null;
    this._renderId = 0;
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("submit", (e) => this._onSubmit(e));
    this.shadowRoot.addEventListener("mousemove", (e) => this._onHover(e));
    this.shadowRoot.addEventListener("mouseleave", () => this._hideTips(), true);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._start();
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    this._narrow = value;
  }

  set panel(value) {
    this._panel = value;
  }

  set route(route) {
    this._route = route;
    if (this.info) this._fromLocation(true);
  }

  connectedCallback() {
    this._timer = setInterval(() => this._tick(), 5 * 60 * 1000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  // ------------------------------------------------------------- data

  /** A cached websocket call. Calls about today expire after five minutes. */
  async get(msg) {
    const key = JSON.stringify(msg);
    const hit = this.cache.get(key);
    const fresh = hit && (!hit.today || Date.now() - hit.at < 5 * 60 * 1000);
    if (fresh) return hit.value;
    const value = await this._hass.callWS(msg);
    const today = this.info ? key.includes(this.info.today) || !/\d{4}-\d{2}-\d{2}/.test(key) : true;
    this.cache.set(key, { value, at: Date.now(), today });
    return value;
  }

  /** An uncached call that changes something; clears the cache afterwards. */
  async call(msg) {
    const result = await this._hass.callWS(msg);
    this.cache.clear();
    return result;
  }

  async callService(domain, service, data = {}) {
    await this._hass.callService(domain, service, data);
    this.cache.clear();
  }

  get settings() {
    return this.info.settings;
  }

  get sources() {
    return this.info.sources;
  }

  get today() {
    return this.info.today;
  }

  get range() {
    return periodRange(this.state.period, this.state.date, this.state.custom);
  }

  async refreshInfo() {
    this.info = await this._hass.callWS({ type: "health_hub/info" });
  }

  toast(text, error = false) {
    const old = this.shadowRoot.querySelector(".toast");
    if (old) old.remove();
    const el = document.createElement("div");
    el.className = `toast${error ? " err" : ""}`;
    el.setAttribute("role", "status");
    el.textContent = text;
    this.shadowRoot.appendChild(el);
    setTimeout(() => el.remove(), error ? 6000 : 2500);
  }

  // ------------------------------------------------------------ routing

  async _start() {
    this.shadowRoot.innerHTML = `<style>${CSS}</style><main><div class="wrap"><p class="loading">Loading your health data…</p></div></main>`;
    try {
      await this.refreshInfo();
    } catch (err) {
      this._fatal(err);
      return;
    }
    this._fromLocation(false);
    window.addEventListener("popstate", () => this._fromLocation(true));
  }

  _fromLocation(rerender) {
    const path = (this._route && this._route.path) || location.pathname.slice(BASE.length) || "/";
    const page = path.split("/").filter(Boolean)[0] || "overview";
    const q = new URLSearchParams(location.search);
    const today = this.info.today;
    let date = q.get("d") || today;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date > today) date = today;
    const period = STEP[q.get("p")] || q.get("p") === "custom" ? q.get("p") : "day";
    const custom = period === "custom" && q.get("s") ? { start: q.get("s"), end: date } : null;
    const next = { page: BY_KEY[page] ? page : "overview", period: period === "custom" && !custom ? "day" : period, date, custom };
    const same = JSON.stringify(next) === JSON.stringify(this.state);
    this.state = next;
    if (!same || !rerender) this.render();
  }

  navigate(changes) {
    this.state = { ...this.state, ...changes };
    const s = this.state;
    const q = new URLSearchParams();
    if (s.period !== "day") q.set("p", s.period);
    if (s.date !== this.info.today) q.set("d", s.date);
    if (s.period === "custom" && s.custom) {
      q.set("s", s.custom.start);
      q.set("d", s.custom.end);
    }
    const url = `${BASE}/${s.page === "overview" ? "" : s.page}${q.toString() ? "?" + q : ""}`;
    history.pushState(null, "", url);
    this.render();
    const main = this.shadowRoot.querySelector("main");
    if (changes.page && main) main.scrollIntoView({ block: "start" });
  }

  _tick() {
    if (!this.info) return;
    const { end } = this.range;
    if (end === this.info.today) {
      for (const [k, v] of this.cache) if (v.today) this.cache.delete(k);
      this.refreshInfo().then(() => this.render(true)).catch(() => {});
    }
  }

  // ------------------------------------------------------------ render

  async render(quiet = false) {
    const id = ++this._renderId;
    const s = this.state;
    const mod = BY_KEY[s.page];
    const root = this.shadowRoot;
    const openDetails = new Set([...root.querySelectorAll("details[data-k][open]")].map((d) => d.dataset.k));
    const closedDetails = new Set([...root.querySelectorAll("details[data-k]:not([open])")].map((d) => d.dataset.k));
    if (!root.querySelector("main .content") || !quiet) {
      root.innerHTML = `<style>${CSS}</style><main><div class="wrap">${this._shell(mod)}<div class="content"><p class="loading">Loading…</p></div></div></main>`;
    }
    let html;
    try {
      const data = await mod.load(this);
      if (id !== this._renderId) return;
      html = mod.render(this, data);
    } catch (err) {
      if (id !== this._renderId) return;
      console.error("Health Hub", err);
      html = `<section class="card"><h2>Couldn't load this page</h2><p class="muted">${h(err && (err.message || err.code) ? err.message || err.code : String(err))}</p></section>`;
    }
    const content = root.querySelector("main .content");
    if (!content) return;
    content.innerHTML = html;
    for (const d of root.querySelectorAll("details[data-k]")) {
      if (openDetails.has(d.dataset.k)) d.open = true;
      if (closedDetails.has(d.dataset.k)) d.open = false;
    }
  }

  _shell(mod) {
    const s = this.state;
    const r = this.range;
    const usesPeriod = mod.usesPeriod !== false;
    const dayOnly = mod.dayOnly === true;
    const period = dayOnly ? "day" : s.period;
    const atEnd = r.end >= this.info.today;
    const sub = mod.title ? mod.title(this) : period === "day" ? longDate(s.date) : rangeLabel(r.start, r.end);
    const tabs = PAGES.map(([k, label]) => `<a href="${BASE}/${k === "overview" ? "" : k}" data-action="page" data-arg="${k}" ${k === s.page ? 'aria-current="page"' : ""}>${h(label)}</a>`).join("");
    const periods = PERIODS.filter(([k]) => !dayOnly || k === "day")
      .map(([k, label]) => `<button data-action="period" data-arg="${k}" aria-pressed="${k === period}">${label}</button>`)
      .join("");
    const custom = s.period === "custom" && !dayOnly
      ? `<form class="custom" data-submit="custom"><label>From <input type="date" name="start" value="${h(r.start)}" max="${h(this.info.today)}"></label><label>to <input type="date" name="end" value="${h(r.end)}" max="${h(this.info.today)}"></label><button class="btn" type="submit">Show</button></form>`
      : "";
    const controls = usesPeriod
      ? `<div class="controls">
          <button class="sq" data-action="prev" aria-label="Earlier">‹</button>
          <div class="seg" role="group" aria-label="Period">${periods}</div>
          <button class="sq" data-action="next" aria-label="Later" ${atEnd ? "disabled" : ""}>›</button>
          ${r.end !== this.info.today ? `<button class="btn" data-action="today">Today</button>` : ""}
          ${this._syncButton()}
        </div>`
      : `<div class="controls">${this._syncButton()}</div>`;
    const stale = FILES_VERSION && this.info.version && FILES_VERSION !== this.info.version && this.info.version !== "preview";
    const banner = stale
      ? `<div class="card soft" role="status" style="flex-direction:row;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px"><span class="small">Health Hub was updated to ${h(this.info.version)}, but this page is still showing ${h(FILES_VERSION)}.</span><button class="btn" data-action="reload">Reload to update</button></div>`
      : "";
    return `${banner}<header class="top">
        <div class="title">
          <button class="menu" data-action="menu" aria-label="Show the Home Assistant menu">☰</button>
          <h1>Health</h1><span class="date">${h(sub)}</span>
        </div>
        ${controls}
      </header>
      ${custom}
      <nav class="tabs" aria-label="Health pages">${tabs}</nav>`;
  }

  /** "Synced 12 min ago", which asks the phone to sync now when clicked. */
  _syncButton() {
    const busy = Boolean(this._syncing);
    const label = busy ? "Syncing…" : `Synced ${relTime(this.info.last_sync)}`;
    const title = busy
      ? "Waiting for your phone to fetch from the band and send the data"
      : "Sync now: ask your phone to fetch the latest data from the band";
    return `<button class="sync" data-action="sync" title="${h(title)}" aria-label="${h(busy ? label : `${label}. Sync now`)}" ${busy ? 'aria-busy="true"' : ""}>${busy ? '<span class="spin" aria-hidden="true"></span>' : '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"></path><path d="M3 21v-5h5"></path><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"></path><path d="M21 3v5h-5"></path></svg>'}<span>${h(label)}</span></button>`;
  }

  _refreshSyncButton() {
    for (const el of this.shadowRoot.querySelectorAll("button.sync")) el.outerHTML = this._syncButton();
  }

  async _syncNow() {
    if (this._syncing) return;
    let asked;
    try {
      asked = await this._hass.callWS({ type: "health_hub/sync/request" });
    } catch (err) {
      this.toast(err && err.message ? err.message : String(err), true);
      return;
    }
    const since = new Date(asked.requested).getTime();
    this._syncing = { since };
    this._refreshSyncButton();
    const deadline = Date.now() + 4 * 60 * 1000;
    const done = (info) => {
      const check = info.last_check && new Date(info.last_check.at).getTime();
      return check && check >= since ? info.last_check : null;
    };
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 4000));
      try {
        await this.refreshInfo();
      } catch (err) {
        continue;
      }
      const check = done(this.info);
      if (check) {
        this._syncing = null;
        this.cache.clear();
        this.toast(check.ok ? check.result || "Synced." : `Sync problem: ${check.result}`, !check.ok);
        await this.render(true);
        this._refreshSyncButton();
        return;
      }
    }
    this._syncing = null;
    this._refreshSyncButton();
    this.toast("Your phone didn't answer within 4 minutes. Check it's online and the Health Hub app is set up.", true);
  }

  _fatal(err) {
    this.shadowRoot.innerHTML = `<style>${CSS}</style><main><div class="wrap"><section class="card"><h2>Health Hub isn't ready</h2><p class="muted">${h(err && err.message ? err.message : String(err))}</p><p class="muted">Check that the Health Hub integration is set up and loaded.</p></section></div></main>`;
  }

  // ------------------------------------------------------------ events

  async _onClick(e) {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const action = el.dataset.action;
    const arg = el.dataset.arg;
    const s = this.state;
    if (action === "page") {
      e.preventDefault();
      if (arg !== s.page) this.navigate({ page: arg });
      return;
    }
    if (action === "reload") {
      location.reload();
      return;
    }
    if (action === "sync") {
      e.preventDefault();
      this._syncNow();
      return;
    }
    if (action === "menu") {
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }));
      return;
    }
    if (action === "period") {
      if (arg === "custom") {
        const r = this.range;
        this.navigate({ period: "custom", custom: { start: r.start === r.end ? addDays(r.end, -13) : r.start, end: r.end }, date: r.end });
      } else {
        this.navigate({ period: arg, custom: null, date: this.range.end });
      }
      return;
    }
    if (action === "prev" || action === "next") {
      const dir = action === "prev" ? -1 : 1;
      const mod = BY_KEY[s.page];
      const period = mod.dayOnly ? "day" : s.period;
      if (period === "custom") {
        const r = this.range;
        const len = daysBetween(r.start, r.end) + 1;
        let end = addDays(r.end, dir * len);
        if (end > this.info.today) end = this.info.today;
        this.navigate({ custom: { start: addDays(end, -(len - 1)), end }, date: end });
      } else {
        let date = addDays(s.date, dir * STEP[period]);
        if (date > this.info.today) date = this.info.today;
        this.navigate({ date });
      }
      return;
    }
    if (action === "today") {
      this.navigate({ date: this.info.today, custom: s.period === "custom" ? null : s.custom, period: s.period === "custom" ? "day" : s.period });
      return;
    }
    if (action === "go") {
      // data-arg="page|period|date"
      const [page, period, date] = arg.split("|");
      this.navigate({ page: page || s.page, period: period || s.period, date: date || s.date, custom: null });
      return;
    }
    const mod = BY_KEY[s.page];
    const handler = mod.actions && mod.actions[action];
    if (!handler) return;
    e.preventDefault();
    el.disabled = true;
    try {
      await handler(this, arg, el);
    } catch (err) {
      this.toast(err && err.message ? err.message : String(err), true);
    } finally {
      el.disabled = false;
    }
  }

  async _onSubmit(e) {
    const form = e.target.closest("form[data-submit]");
    if (!form) return;
    e.preventDefault();
    const name = form.dataset.submit;
    const data = Object.fromEntries(new FormData(form).entries());
    if (name === "custom") {
      let { start, end } = data;
      if (!start || !end) return;
      if (end > this.info.today) end = this.info.today;
      if (start > end) [start, end] = [end, start];
      if (daysBetween(start, end) > 399) start = addDays(end, -399);
      this.navigate({ period: "custom", custom: { start, end }, date: end });
      return;
    }
    const mod = BY_KEY[this.state.page];
    const handler = mod.actions && mod.actions[name];
    if (!handler) return;
    const button = form.querySelector("[type=submit]");
    if (button) button.disabled = true;
    try {
      await handler(this, data, form);
    } catch (err) {
      this.toast(err && err.message ? err.message : String(err), true);
    } finally {
      if (button) button.disabled = false;
    }
  }

  _onHover(e) {
    const box = e.target.closest && e.target.closest(".hov");
    if (!box) {
      this._hideTips();
      return;
    }
    if (!box._series) box._series = JSON.parse(box.dataset.series || "[]");
    const series = box._series;
    if (!series.length) return;
    const rect = box.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const x0 = Number(box.dataset.x0);
    const x1 = Number(box.dataset.x1);
    const x = x0 + frac * (x1 - x0);
    let lo = 0;
    let hi = series.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (series[mid][0] < x) lo = mid;
      else hi = mid;
    }
    const best = Math.abs(series[lo][0] - x) <= Math.abs(series[hi][0] - x) ? series[lo] : series[hi];
    const tip = box.querySelector(".tip");
    tip.hidden = false;
    tip.textContent = best[1];
    tip.style.left = `${(((best[0] - x0) / (x1 - x0)) * 100).toFixed(2)}%`;
    if (this._tipBox && this._tipBox !== box) this._hideTips();
    this._tipBox = box;
  }

  _hideTips() {
    if (this._tipBox) {
      const tip = this._tipBox.querySelector(".tip");
      if (tip) tip.hidden = true;
      this._tipBox = null;
    }
  }
}

if (!customElements.get("health-hub-panel")) customElements.define("health-hub-panel", HealthHubPanel);
