// Small helpers shared by every page. No dependencies.

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape text for HTML. Everything that comes from data goes through this. */
export function h(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (c) => ESC[c]);
}

export const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function num(v, digits = 0) {
  if (!isNum(v)) return "–";
  return v.toLocaleString("en-AU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Minutes as "7h 13m" / "45m". */
export function dur(min) {
  if (!isNum(min)) return "–";
  const m = Math.round(Math.abs(min));
  const hh = Math.floor(m / 60);
  const mm = m % 60;
  const sign = min < 0 ? "−" : "";
  return hh ? `${sign}${hh}h ${String(mm).padStart(2, "0")}m` : `${sign}${mm}m`;
}

/** "23:05" → "11:05pm". */
export function clock12(hhmm) {
  if (!hhmm) return "–";
  const [hs, ms] = hhmm.split(":");
  const hr = Number(hs);
  const suffix = hr < 12 ? "am" : "pm";
  return `${hr % 12 || 12}:${ms}${suffix}`;
}

/** Minutes after midday → "11:05pm". */
export function clockFromNoon(m) {
  if (!isNum(m)) return "–";
  const t = (Math.round(m) + 720) % 1440;
  return clock12(`${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`);
}

/** Minute of day → "3pm" style axis label. */
export function hourLabel(minute) {
  const hr = Math.floor(minute / 60) % 24;
  return `${hr % 12 || 12}${hr < 12 ? "am" : "pm"}`;
}

// ------------------------------------------------------------------ dates
// Dates travel as "YYYY-MM-DD" strings in Home Assistant's time zone; maths is
// done on UTC dates so the browser's own time zone never matters.

export function parseDate(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function fmtDate(d) {
  return d.toISOString().slice(0, 10);
}

export function addDays(s, n) {
  const d = parseDate(s);
  d.setUTCDate(d.getUTCDate() + n);
  return fmtDate(d);
}

export function daysBetween(a, b) {
  return Math.round((parseDate(b) - parseDate(a)) / 86400000);
}

export function weekday(s) {
  return (parseDate(s).getUTCDay() + 6) % 7; // Monday = 0
}

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export const dayName = (s, short = false) => (short ? DAYS[weekday(s)].slice(0, 3) : DAYS[weekday(s)]);

export function longDate(s, withYear = false) {
  const d = parseDate(s);
  return `${DAYS[weekday(s)]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${withYear ? " " + d.getUTCFullYear() : ""}`;
}

export function shortDate(s, withYear = false) {
  const d = parseDate(s);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()].slice(0, 3)}${withYear ? " " + d.getUTCFullYear() : ""}`;
}

export function monthName(i, short = true) {
  return short ? MONTHS[i].slice(0, 3) : MONTHS[i];
}

/** The date range a period covers, ending on (and including) `date`. */
export function periodRange(period, date, custom) {
  if (period === "custom" && custom) return { start: custom.start, end: custom.end };
  if (period === "week") return { start: addDays(date, -6), end: date };
  if (period === "month") return { start: addDays(date, -29), end: date };
  if (period === "year") return { start: addDays(date, -364), end: date };
  return { start: date, end: date };
}

export function rangeLabel(start, end) {
  const a = parseDate(start);
  const b = parseDate(end);
  const sameYear = a.getUTCFullYear() === b.getUTCFullYear();
  if (start === end) return longDate(start, !sameYear);
  if (sameYear && a.getUTCMonth() === b.getUTCMonth()) {
    return `${a.getUTCDate()}–${b.getUTCDate()} ${MONTHS[b.getUTCMonth()]}`;
  }
  return `${shortDate(start, !sameYear)} – ${shortDate(end, !sameYear)}`;
}

export function mean(values) {
  const v = values.filter(isNum);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

export function sum(values) {
  return values.filter(isNum).reduce((a, b) => a + b, 0);
}

export function relTime(iso) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}
