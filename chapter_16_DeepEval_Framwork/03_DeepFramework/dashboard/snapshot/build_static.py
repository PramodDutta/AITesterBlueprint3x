"""Bake results.json into a self-contained static showcase for Vercel.

Same grid, same numbers, no backend and no API key. Run buttons become a
"recorded" badge, because a static page cannot call a judge. The Details
drill-down still works: every per-case row is embedded in the page.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
DIST = HERE / "dist"
DATA = json.loads((HERE / "results.json").read_text())

CSS = (ROOT / "dashboard" / "static" / "style.css").read_text()


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def fmt(score) -> str:
    return "&ndash;" if score is None else f"{score:.3f}"


def card_html(card: dict, res: dict | None) -> str:
    cat = card["category"]
    cat_label = "G-Eval" if cat == "geval" else cat
    status = (res or {}).get("status", "idle")
    score = (res or {}).get("score")
    reason = (res or {}).get("reason") or card["question"]
    tokens = (res or {}).get("tokens") or {}
    pct = 0 if score is None else max(0.0, min(1.0, score)) * 100
    gate = card["threshold"] * 100
    rows = (res or {}).get("rows") or []

    meta = (
        f'{(res or {}).get("latency_ms", 0)} ms &middot; '
        f'{(res or {}).get("cases_run", 0)}/{card["cases_total"]} cases'
    )
    tok = (
        f'{tokens.get("total", 0):,} tokens &middot; '
        f'target {tokens.get("target", {}).get("total", 0):,} &middot; '
        f'judge {tokens.get("judge", {}).get("total", 0):,}'
        if tokens else "&mdash;"
    )
    return f'''
    <article class="card" data-key="{esc(card["key"])}" data-cat="{esc(cat)}"
             data-target="{esc(card["target"])}" data-status="{esc(status)}">
      <div class="top">
        <span class="tag {esc(cat)}">{esc(cat_label)}</span>
        <span class="tag target">{esc(card["target"])}</span>
        <span class="thr">&ge; {card["threshold"]:.2f}</span>
      </div>
      <h3>{esc(card["title"])}</h3>
      <p class="blurb">{esc(card["blurb"])}</p>
      <div class="result">
        <div class="head">
          <span class="badge {esc(status)}">{esc(status.upper())}</span>
          <div class="cmp">
            <span class="num"><b class="score {esc(status)}">{fmt(score)}</b><i>score</i></span>
            <span class="op">&ge;</span>
            <span class="num"><b class="thr-val">{card["threshold"]:.2f}</b><i>threshold</i></span>
          </div>
        </div>
        <div class="bar">
          <i class="fill {'' if status == 'pass' else 'fail'}" style="width:{pct:.1f}%"></i>
          <u class="gate" style="left:{gate:.1f}%"></u>
        </div>
        <p class="hint">{esc(card.get("scale_hint", ""))}</p>
        <p class="reason">{esc(reason)}</p>
        <div class="meta">{meta}</div>
        <div class="meta tok">{tok}</div>
      </div>
      <div class="actions">
        <span class="btn btn-recorded">&#9673; Recorded</span>
        <button class="btn btn-outline details"{"" if rows else " disabled"}>Details</button>
      </div>
    </article>'''


cards = DATA["cards"]
results = DATA["results"]
n_pass = sum(1 for c in cards if results.get(c["key"], {}).get("status") == "pass")
n_fail = sum(1 for c in cards if results.get(c["key"], {}).get("status") == "fail")
n_err = len(cards) - n_pass - n_fail
tot = DATA["tokens"]

details = {
    c["key"]: {
        "title": c["title"],
        "threshold": c["threshold"],
        "rows": results.get(c["key"], {}).get("rows", []),
        "latency_ms": results.get(c["key"], {}).get("latency_ms", 0),
        "cases_total": c["cases_total"],
    }
    for c in cards
}

page = f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeepEval Dashboard &middot; Recorded Run</title>
<meta name="description" content="A recorded run of 25 DeepEval metrics against a live chatbot and RAG pipeline.">
<style>
{CSS}
.btn-recorded{{background:var(--panel);border:1px dashed var(--line);color:var(--muted);
  text-align:center;cursor:default;font-weight:600;line-height:1.3}}
.snapshot-note{{background:#FBF0D9;border:1px solid #E8D6A8;color:#6B4E12;
  border-radius:9px;padding:13px 18px;margin-bottom:20px;font-size:14px;line-height:1.55}}
.snapshot-note b{{display:block;margin-bottom:2px}}
.snapshot-note a{{color:#8A5A12}}
@media (prefers-color-scheme:dark){{
  .snapshot-note{{background:#2C2418;border-color:#4A3A1C;color:#E5CE9A}}
  .snapshot-note a{{color:#E9B85C}}
}}
</style>
</head><body>

<header class="topbar">
  <div class="brand">
    <div class="logo">&#9670;</div>
    <div>
      <h1>DeepEval Dashboard</h1>
      <p>Recorded run &middot; chatbot and RAG pipeline graded by a judge model</p>
    </div>
  </div>
  <div class="ctl">
    <label for="target">Target</label>
    <select id="target">
      <option value="all" selected>All targets</option>
      <option value="chatbot">Chatbot (A)</option>
      <option value="rag">RAG (B)</option>
    </select>
  </div>
  <div class="ctl">
    <label for="judge">Judge model</label>
    <input id="judge" value="{esc(DATA['status']['judge']['model'])}" readonly>
  </div>
</header>

<div class="wrap">
  <div class="snapshot-note">
    <b>This is a recorded run, not a live one.</b>
    Every score, reason, latency and token count below came from one real execution on
    {esc(DATA["captured_at"][:10])} against a running chatbot and RAG pipeline, judged by
    {esc(DATA['status']['judge']['model'])}. A static page cannot call a model, so the
    Run buttons are replaced by a Recorded badge &mdash; everything else, including the
    per-case Details, is the real output.
    <a href="/how-it-works">Read how the framework works</a>, or
    <a href="https://github.com/PramodDutta/AITesterBlueprint3x/tree/main/chapter_16_DeepEval_Framwork">clone
    the repo</a> to run it live.
  </div>

  <section class="status">
    <div class="stat">
      <div class="row"><span class="dot up"></span><b>Chatbot</b></div>
      <code>subsystem A &middot; qwen/qwen3.8-27b</code>
    </div>
    <div class="stat">
      <div class="row"><span class="dot up"></span><b>RAG</b></div>
      <code>subsystem B &middot; nomic-embed + Chroma</code>
    </div>
    <div class="stat">
      <div class="row"><span class="dot up"></span><b>Judge</b></div>
      <code>groq &middot; {esc(DATA['status']['judge']['model'])}</code>
    </div>
    <div class="stat">
      <div class="row"><span class="dot up"></span><b>Tokens used</b></div>
      <code>{tot['total']:,} total &middot; {tot['calls']} calls</code>
      <code class="split">target {tot['target']['total']:,} &middot; judge {tot['judge']['total']:,}</code>
    </div>
    <div class="stat counts">
      <span class="lbl">pass &middot; fail &middot; error</span>
      <span class="pills">
        <span class="pill p" id="n-pass">{n_pass}</span>
        <span class="pill f" id="n-fail">{n_fail}</span>
        <span class="pill n" id="n-pending">{n_err}</span>
      </span>
    </div>
  </section>

  <div class="filters">
    <span>Categories:</span>
    {"".join(f'<button class="chip {"on" if c == "all" else ""}" data-cat="{c}">'
             f'{"All" if c == "all" else ("G-Eval" if c == "geval" else c.capitalize())}</button>'
             for c in DATA["categories"])}
  </div>

  <section class="grid" id="grid">
    {"".join(card_html(c, results.get(c["key"])) for c in cards)}
  </section>
</div>

<div class="mask" id="mask">
  <div class="modal">
    <button class="close" id="close">&times;</button>
    <h2 id="m-title">Metric</h2>
    <p class="sub" id="m-sub"></p>
    <div id="m-body"></div>
  </div>
</div>

<script>
const DETAILS = {json.dumps(details)};
const $  = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];
const fmt = n => (n === null || n === undefined) ? '–' : n.toFixed(3);
const esc = s => String(s).replace(/[&<>"']/g, c =>
  ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));

function applyFilters(){{
  const cat = $('.chip.on').dataset.cat, tgt = $('#target').value;
  $$('.card').forEach(c => c.classList.toggle('hide',
    !((cat === 'all' || c.dataset.cat === cat) &&
      (tgt === 'all' || c.dataset.target === tgt))));
  const vis = $$('.card').filter(c => !c.classList.contains('hide'));
  const by = s => vis.filter(c => c.dataset.status === s).length;
  $('#n-pass').textContent = by('pass');
  $('#n-fail').textContent = by('fail');
  $('#n-pending').textContent = vis.length - by('pass') - by('fail');
}}

$$('.chip').forEach(ch => ch.onclick = () => {{
  $$('.chip').forEach(c => c.classList.remove('on'));
  ch.classList.add('on'); applyFilters();
}});
$('#target').onchange = applyFilters;

$$('.card').forEach(card => {{
  const btn = $('.details', card);
  if (!btn || btn.disabled) return;
  btn.onclick = () => {{
    const d = DETAILS[card.dataset.key];
    $('#m-title').textContent = d.title;
    $('#m-sub').textContent =
      `${{d.rows.length}} of ${{d.cases_total}} cases · threshold ≥ ${{d.threshold}} · ${{d.latency_ms}} ms`;
    $('#m-body').innerHTML = d.rows.map(row => `
      <div class="case">
        <div class="h">
          <span class="badge ${{row.passed ? 'pass' : 'fail'}}">${{row.passed ? 'PASS' : 'FAIL'}}</span>
          <span class="score ${{row.passed ? 'pass' : 'fail'}}">${{fmt(row.score)}}</span>
          <span class="vs">&ge; ${{d.threshold.toFixed(2)}}</span>
          <span class="q">${{esc(row.label)}}</span>
        </div>
        <pre>${{esc(row.actual_output || '(empty reply)')}}</pre>
        <p class="why">${{esc(row.reason || '')}}</p>
      </div>`).join('') || '<p>No cases recorded.</p>';
    $('#mask').classList.add('on');
  }};
}});
$('#close').onclick = () => $('#mask').classList.remove('on');
$('#mask').onclick = e => {{ if (e.target.id === 'mask') $('#mask').classList.remove('on'); }};
applyFilters();
</script>
</body></html>'''

DIST.mkdir(parents=True, exist_ok=True)
(DIST / "index.html").write_text(page)

# ---------------------------------------------------------------------------
# Second page: the illustrated walkthrough. It is authored as a fragment (no
# <html>/<head>), so wrap it before hosting it standalone.
# ---------------------------------------------------------------------------
EXPLAINER_SRC = ROOT.parent / "How_The_DeepEval_Framework_Works.html"
if EXPLAINER_SRC.exists():
    frag = EXPLAINER_SRC.read_text()
    nav = '''<div style="position:sticky;top:0;z-index:20;background:var(--paper);
     border-bottom:2px solid var(--ink);padding:10px 24px;display:flex;gap:18px;
     align-items:center;font-family:var(--sans);font-size:14px">
  <strong style="font-weight:600">DeepEval Framework</strong>
  <a href="/" style="color:var(--blue);text-decoration:none">&larr; the dashboard</a>
  <a href="https://github.com/PramodDutta/AITesterBlueprint3x/tree/main/chapter_16_DeepEval_Framwork"
     style="color:var(--blue);text-decoration:none;margin-left:auto">source on GitHub</a>
</div>'''
    wrapped = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="description" content="How a judge model grades a chatbot and a '
        'RAG pipeline: the evaluation loop, 25 metrics, and the four ways the scores mislead you.">\n'
        '<style>body{margin:0}img{max-width:100%}</style>\n'
        + frag.replace("<title>", "<title>", 1)
        + "\n</head>\n<body>\n</body>\n</html>\n"
    )
    # The fragment carries its own <title>, <style> and markup in document
    # order; splitting on the first tag after the styles keeps that intact.
    marker = '<svg width="0" height="0"'
    head_part, _, body_part = frag.partition(marker)
    wrapped = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="description" content="How a judge model grades a chatbot and a '
        'RAG pipeline: the evaluation loop, 25 metrics, and the four ways the scores mislead you.">\n'
        '<style>body{margin:0}img{max-width:100%}</style>\n'
        + head_part
        + '</head>\n<body>\n' + nav + '\n' + marker + body_part
        + '\n</body>\n</html>\n'
    )
    (DIST / "how-it-works.html").write_text(wrapped)
    print(f"built {DIST/'how-it-works.html'}  "
          f"({(DIST/'how-it-works.html').stat().st_size/1024:.0f} KB)")
(HERE / "vercel.json").write_text(json.dumps({
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "outputDirectory": "dist",
    "cleanUrls": True,
}, indent=2) + "\n")
kb = (DIST / "index.html").stat().st_size / 1024
print(f"built {DIST/'index.html'}  ({kb:.0f} KB)")
print(f"  {len(cards)} cards | {n_pass} pass, {n_fail} fail, {n_err} error")
print(f"  {tot['total']:,} tokens (target {tot['target']['total']:,} / judge {tot['judge']['total']:,})")
