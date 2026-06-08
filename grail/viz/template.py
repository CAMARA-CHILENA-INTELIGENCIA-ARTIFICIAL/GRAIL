"""
Self-contained HTML viewer template.

Provided by Nirvai (Nirvana). Author: Benjamín González Guerrero.

The renderer itself lives in TypeScript under ``grail/viz/web/`` and is
prebuilt to ``grail/viz/web/dist/grail-viz.umd.cjs`` + ``grail-viz.css``.
This module embeds those artefacts inline so the produced HTML opens
offline — no CDN required.

Build the artefacts once::

    cd grail/viz/web
    npm install
    npm run build

After that, every call to :func:`render_html` reads the built JS + CSS off
disk and inlines them.
"""
from __future__ import annotations

import datetime
import html
import json
import logging
from importlib import resources
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DIST_DIR = Path(__file__).parent / "web" / "dist"
_RENDERER_JS_NAME = "grail-viz.umd.cjs"
_RENDERER_CSS_NAME = "grail-viz.css"


class RendererBundleMissing(RuntimeError):
    """Raised when the prebuilt renderer bundle cannot be located on disk."""


def render_html(
    graph_payload: dict[str, Any],
    *,
    title: str = "GRAIL Knowledge Graph",
    project_name: str = "",
    run_id: str = "",
) -> str:
    """Render the standalone HTML viewer.

    Reads the prebuilt UMD bundle and CSS from ``grail/viz/web/dist/`` and
    inlines them. The graph payload is exposed to the renderer as
    ``window.__GRAIL_VIZ_PAYLOAD__``.
    """
    bundle_js, bundle_css = _load_renderer_assets()
    safe_title = html.escape(title)
    safe_project = html.escape(project_name) or "—"
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    payload_json = json.dumps(graph_payload, ensure_ascii=False, default=_json_default)

    return _TEMPLATE.format(
        title=safe_title,
        project=safe_project,
        run_suffix=_format_run_suffix(run_id),
        generated_at=generated_at,
        payload_json=payload_json,
        renderer_css=bundle_css,
        renderer_js=bundle_js,
    )


def _format_run_suffix(run_id: str) -> str:
    if not run_id:
        return ""
    return f" · <strong>{html.escape(run_id)}</strong>"


def _load_renderer_assets() -> tuple[str, str]:
    """Return ``(js, css)`` for the prebuilt renderer bundle.

    Prefers the on-disk ``dist/`` folder beside this module (covers editable
    installs and source checkouts). Falls back to package resources so wheels
    that ship the dist folder still work.
    """
    js_path = _DIST_DIR / _RENDERER_JS_NAME
    css_path = _DIST_DIR / _RENDERER_CSS_NAME
    if js_path.is_file() and css_path.is_file():
        return js_path.read_text(encoding="utf-8"), css_path.read_text(encoding="utf-8")

    try:
        web_dist = resources.files("grail.viz") / "web" / "dist"
        js = (web_dist / _RENDERER_JS_NAME).read_text(encoding="utf-8")
        css = (web_dist / _RENDERER_CSS_NAME).read_text(encoding="utf-8")
        return js, css
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RendererBundleMissing(
            "The prebuilt grail-viz renderer was not found. Build it first: "
            "`cd grail/viz/web && npm install && npm run build`."
        ) from exc


def _json_default(obj: Any) -> Any:
    """Make numpy scalars / ndarrays / pandas types JSON-serialisable."""
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


# ── Template ──────────────────────────────────────────────────────────────
# str.format is used; every literal `{` and `}` in CSS/JS is doubled.

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --gv-header-bg: #131722;
  --gv-header-border: #262c3b;
  --gv-header-text: #f1f3f8;
  --gv-header-dim: #b4bccc;
  --gv-footer-bg: #131722;
  --gv-footer-border: #262c3b;
  --gv-footer-text: #b4bccc;
  --gv-accent: #a78bfa;
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0;
  height: 100vh; width: 100vw;
  overflow: hidden;
  background: #0b0d12;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 13px;
  color: #f1f3f8;
  -webkit-font-smoothing: antialiased;
}}
#app {{
  display: grid;
  grid-template-rows: 44px 1fr 28px;
  grid-template-columns: 1fr 360px;
  height: 100vh;
  width: 100vw;
}}
header {{
  grid-column: 1 / 3;
  display: flex;
  align-items: center;
  padding: 0 16px;
  background: var(--gv-header-bg);
  border-bottom: 1px solid var(--gv-header-border);
  gap: 12px;
}}
header .logo {{
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--gv-accent);
}}
header .crumb {{
  color: var(--gv-header-dim);
  font-size: 12px;
}}
header .crumb strong {{
  color: var(--gv-header-text);
  font-weight: 600;
}}
#canvas {{
  position: relative;
  overflow: hidden;
}}
#sidebar {{
  overflow: auto;
}}
footer {{
  grid-column: 1 / 3;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: var(--gv-footer-bg);
  border-top: 1px solid var(--gv-footer-border);
  color: var(--gv-footer-text);
  font-size: 11px;
}}
footer button {{
  background: transparent;
  color: var(--gv-footer-text);
  border: 1px solid var(--gv-footer-border);
  border-radius: 4px;
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}}
footer button:hover {{
  color: var(--gv-header-text);
  border-color: var(--gv-accent);
}}
#loading {{
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gv-header-dim);
  pointer-events: none;
}}
{renderer_css}
</style>
</head>
<body class="grail-viz">
<div id="app">
  <header>
    <span class="logo">GRAIL</span>
    <span class="crumb">Knowledge Graph · <strong>{project}</strong>{run_suffix}</span>
  </header>
  <div id="canvas">
    <div id="loading">Loading graph…</div>
  </div>
  <div id="sidebar"></div>
  <footer>
    <span>Generated {generated_at}</span>
    <button id="relayout" type="button">Re-layout</button>
  </footer>
</div>

<script id="grail-viz-payload" type="application/json">{payload_json}</script>

<script>
{renderer_js}
</script>

<script>
(function () {{
  var payload = JSON.parse(document.getElementById("grail-viz-payload").textContent);
  window.__GRAIL_VIZ_PAYLOAD__ = payload;
  var canvas = document.getElementById("canvas");
  var sidebar = document.getElementById("sidebar");
  var loading = document.getElementById("loading");

  if (!window.GrailViz || typeof window.GrailViz.mount !== "function") {{
    if (loading) loading.textContent = "Renderer failed to load. Rebuild grail/viz/web (npm run build).";
    return;
  }}

  if (loading && loading.parentNode === canvas) canvas.removeChild(loading);

  var handle = window.GrailViz.mount(canvas, sidebar, payload);
  window.__GRAIL_VIZ_HANDLE__ = handle;

  var relayoutBtn = document.getElementById("relayout");
  if (relayoutBtn) {{
    relayoutBtn.addEventListener("click", function () {{
      handle.renderer.relayout();
    }});
  }}
}})();
</script>
</body>
</html>
"""
