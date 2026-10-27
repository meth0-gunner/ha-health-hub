// The page's look: dark and calm, desktop first, works down to phone width.
export const CSS = `
:host {
  --font: Inter, "Segoe UI", Roboto, system-ui, sans-serif;
  --bg: #0F1218; --card: #171B23; --card2: #131820; --inset: #11151C; --line: #222834; --edge: #2A303C;
  --track: #252B36; --text: #E7EAF0; --soft: #C9CFDA; --muted: #A3ACBA; --faint: #8A93A3; --dim: #5C6474;
  --link: #9DB8FF; --teal: #4FD1C5; --amber: #F2A65A; --blue: #6EA8FE; --rose: #F7768E; --violet: #A78BFA; --gold: #F2C94C;
  display: block; min-height: 100vh; background: var(--bg); color: var(--text);
  font-family: var(--font); font-feature-settings: "tnum" 1; -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
a { color: var(--link); text-decoration: none; } a:hover { color: #C3D3FF; }
button { font: inherit; color: inherit; }
main { padding: 20px 24px 56px; }
.wrap { max-width: 1360px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }

/* top bar */
.top { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; }
.title { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
.title h1 { margin: 0; font-size: 28px; font-weight: 600; letter-spacing: -0.01em; }
.title .date { font-size: 15px; color: var(--muted); }
.menu { width: 44px; height: 44px; border-radius: 10px; border: 1px solid var(--edge); background: var(--card); cursor: pointer; display: none; }
.controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sq { width: 44px; height: 44px; border-radius: 10px; border: 1px solid var(--edge); background: var(--card); color: var(--text); font-size: 18px; cursor: pointer; }
.sq:disabled { color: var(--dim); cursor: default; }
.seg { display: flex; background: var(--card); border: 1px solid var(--edge); border-radius: 12px; padding: 4px; gap: 2px; }
.seg button { min-height: 36px; padding: 0 14px; border: 0; border-radius: 8px; background: transparent; color: var(--muted); font-weight: 500; font-size: 14px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: #2A3242; color: var(--text); }
.sync { font-size: 13px; color: var(--muted); }
.custom { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 13px; color: var(--muted); }
input, select { font: inherit; color: var(--text); background: var(--inset); border: 1px solid var(--edge); border-radius: 10px; min-height: 40px; padding: 0 10px; }
input[type="date"], input[type="time"] { color-scheme: dark; }

/* page tabs */
nav.tabs { display: flex; gap: 4px; flex-wrap: wrap; border-bottom: 1px solid var(--line); }
nav.tabs a { padding: 12px 14px; color: var(--muted); font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent; min-height: 44px; display: inline-flex; align-items: center; }
nav.tabs a[aria-current="page"] { color: var(--text); border-bottom-color: var(--blue); }

/* cards */
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
.grid.small { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
.row { display: flex; flex-wrap: wrap; gap: 20px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 24px; display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.card.tight { padding: 20px 24px; gap: 6px; }
.card.soft { background: var(--card2); border-radius: 16px; padding: 18px 20px; }
.card.night { background: #1A1830; border-color: #332C5C; }
.head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
h2 { margin: 0; font-size: 15px; font-weight: 600; color: var(--soft); }
h3 { margin: 0; font-size: 13px; font-weight: 500; color: var(--muted); }
.muted { color: var(--muted); } .faint { color: var(--faint); } .soft { color: var(--soft); }
.small { font-size: 13px; } .tiny { font-size: 12px; }
.big { font-size: 28px; font-weight: 600; }
.huge { font-size: 56px; font-weight: 600; line-height: 1; }
.num { font-size: 22px; font-weight: 600; }
.center { text-align: center; align-items: center; }
p { margin: 0; line-height: 1.5; }
.lead { font-size: 14px; color: var(--soft); }
.empty { color: var(--muted); font-size: 14px; padding: 8px 0; }
.stat { display: flex; flex-direction: column; gap: 2px; }
.stat .k { font-size: 12px; color: var(--muted); } .stat .v { font-size: 17px; font-weight: 600; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; border-top: 1px solid var(--line); padding-top: 14px; }

/* meters */
ul.meters { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
li.meter { display: grid; grid-template-columns: 130px 1fr 96px; align-items: center; gap: 12px; font-size: 13px; }
.track { height: 6px; border-radius: 3px; background: var(--track); display: block; }
.track > span { display: block; height: 6px; border-radius: 3px; }
.right { text-align: right; }

/* "Why?" */
details.why { font-size: 13px; color: var(--soft); }
details.why > summary { min-height: 44px; display: flex; align-items: center; cursor: pointer; color: var(--link); list-style: none; }
details.why > summary::-webkit-details-marker { display: none; }
details.why.c > summary { justify-content: center; }
details.why .box { background: var(--inset); border: 1px solid #262D3A; border-radius: 12px; padding: 12px 14px; line-height: 1.5; display: flex; flex-direction: column; gap: 6px; }

/* buttons */
.btn { min-height: 44px; padding: 0 16px; border-radius: 12px; border: 1px solid #3A4456; background: #1E2430; color: var(--text); font-weight: 500; font-size: 14px; cursor: pointer; }
.btn.big { min-height: 56px; font-weight: 600; font-size: 15px; }
.btn.gold { border-color: var(--gold); background: transparent; color: var(--gold); font-weight: 600; }
.btn:disabled { opacity: 0.5; cursor: default; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; border-radius: 999px; padding: 4px 6px 4px 12px; }
.chip button { width: 28px; height: 28px; border: 0; border-radius: 999px; background: transparent; color: inherit; cursor: pointer; }
.chip.gym { background: #2A2440; color: #D8CCFF; } .chip.compex { background: #1E3036; color: #B2F5EA; }
.pill { align-self: flex-start; font-size: 12px; font-weight: 600; border-radius: 999px; padding: 2px 10px; color: #0F1218; }
.pill.good { background: var(--teal); } .pill.watch { background: var(--amber); } .pill.see_doctor { background: var(--rose); }
.pill.neutral, .pill.info { background: #2E3644; color: var(--text); }
.tag { font-size: 12px; color: var(--muted); border: 1px solid var(--edge); border-radius: 999px; padding: 3px 10px; }

/* charts */
svg.wide { width: 100%; display: block; }
.axis { display: flex; justify-content: space-between; font-size: 12px; color: var(--faint); padding-top: 6px; }
.legend { display: flex; gap: 16px; font-size: 12px; color: var(--muted); flex-wrap: wrap; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
.legend i.dash { width: 14px; height: 0; border-top: 2px dashed; border-radius: 0; vertical-align: middle; }
.lanes { display: grid; grid-template-columns: 92px 1fr; gap: 6px 12px; align-items: center; }
.lanes > .lab { font-size: 12px; color: var(--muted); }
.lanes > .lab b { display: block; font-size: 15px; color: var(--text); font-weight: 600; }
.colchart { display: grid; grid-template-columns: 40px 1fr; gap: 0 10px; }
.ylabels { position: relative; font-size: 12px; color: var(--faint); }
.ylabels span { position: absolute; right: 0; transform: translateY(-50%); }
.xlabels { display: grid; font-size: 12px; color: var(--muted); text-align: center; padding-top: 6px; }
.xlabels.tops { padding: 0 0 4px; font-weight: 600; }
.xlabels .now { color: var(--text); font-weight: 600; }
.plot { position: relative; }
.hits { position: absolute; inset: 0; display: grid; }
.hit { background: transparent; border: 0; cursor: pointer; }
.hit:hover { background: rgba(255,255,255,0.04); }
.hov { position: relative; }
.tip { position: absolute; top: -6px; transform: translate(-50%, -100%); background: #262D3A; color: var(--text); font-size: 12px; padding: 4px 8px; border-radius: 6px; pointer-events: none; white-space: nowrap; }
.lanes4 { display: flex; flex-direction: column; justify-content: space-around; font-size: 12px; color: var(--muted); }

/* tables */
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; color: var(--muted); font-weight: 500; padding: 6px 8px; }
td { padding: 6px 8px; border-top: 1px solid var(--line); }

/* review */
ul.obs { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 14px; }
ul.obs > li { background: var(--card2); border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px; display: flex; flex-direction: column; gap: 8px; }
.headline { font-size: 22px; font-weight: 600; line-height: 1.35; }

/* training */
.blocks { display: grid; gap: 4px; }
.blocks span { height: 14px; border-radius: 4px; background: var(--track); }
.weeks { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; font-size: 12px; color: var(--muted); text-align: center; }
.weeks > div { background: #1E2430; border-radius: 10px; padding: 8px 4px; }
.weeks > div.now { border: 1px solid #3A4456; }
.weeks > div.future { background: #161A21; }
.weeks b { display: block; color: var(--text); font-size: 14px; font-weight: 600; }
.cal { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }
.cal > div { background: var(--card2); border: 1px solid var(--line); border-radius: 10px; min-height: 76px; padding: 6px; display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.cal > div.today { border-color: var(--blue); }
.cal > div.future { opacity: 0.45; }
.cal .d { color: var(--muted); }
.cal .g { background: #2A2440; color: #D8CCFF; border-radius: 6px; padding: 1px 6px; }
.cal .c { background: #1E3036; color: #B2F5EA; border-radius: 6px; padding: 1px 6px; }
.reward { background: #1E2430; border-radius: 16px; padding: 20px; display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }

form.settings { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
form .settings label, form.settings label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
form .settings .hint, form.settings .hint { font-size: 12px; color: var(--faint); }
.inline { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #262D3A; color: var(--text); padding: 10px 16px; border-radius: 10px; font-size: 14px; z-index: 10; }
.toast.err { background: #4A2430; }
.loading { color: var(--muted); padding: 40px 0; text-align: center; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

@media (max-width: 720px) {
  main { padding: 12px 16px 40px; }
  .menu { display: inline-block; }
  li.meter { grid-template-columns: 110px 1fr 80px; }
  .huge { font-size: 44px; }
  .lanes { grid-template-columns: 70px 1fr; }
  .cal > div { min-height: 56px; }
}
`;
