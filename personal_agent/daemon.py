from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .runtime import PersonalAgentRuntime


HTML_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>personal-agent / codex runner</title>
    <style>
      :root {
        --bg: #f5f1ea;
        --panel: #fffaf2;
        --ink: #1f1a16;
        --muted: #6c655d;
        --line: #dccdb9;
        --accent: #0e6b55;
        --warn: #9d3c2a;
        --info: #1f5f99;
      }
      body { margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: linear-gradient(180deg, #ede4d7, #f7f3ed); color: var(--ink); }
      header, main { max-width: 1240px; margin: 0 auto; padding: 24px; }
      h1, h2, h3, p { margin-top: 0; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; align-items: start; }
      .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 12px 28px rgba(57, 44, 24, 0.08); min-height: 220px; }
      .muted, .meta { color: var(--muted); }
      .warn { color: var(--warn); }
      ul { padding-left: 18px; margin: 0; }
      li { margin-bottom: 12px; }
      textarea, input, button { font: inherit; }
      textarea, input { width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid var(--line); padding: 10px 12px; background: white; }
      textarea { min-height: 88px; }
      button { border: 0; background: var(--accent); color: white; padding: 10px 14px; border-radius: 999px; cursor: pointer; width: fit-content; }
      .secondary { background: var(--info); }
      .danger { background: var(--warn); }
      form { display: flex; flex-direction: column; gap: 8px; }
      a { color: var(--info); text-decoration: none; }
      a:hover { text-decoration: underline; }
      code, pre { font-family: ui-monospace, SFMono-Regular, monospace; }
      pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f1e8; border: 1px solid var(--line); border-radius: 12px; padding: 12px; }
      .pill { display: inline-block; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); background: white; font-size: 0.8rem; }
      .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
      .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 18px 0 0; }
      .summary-card { background: rgba(255, 250, 242, 0.72); border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; min-height: 72px; box-sizing: border-box; }
      .summary-card strong { display: block; font-size: 1.5rem; line-height: 1; margin-bottom: 6px; }
      .summary-card span { display: block; min-height: 1.2em; }
      .list-slot { min-height: 160px; }
      .empty-state { min-height: 132px; display: flex; align-items: center; }
      .item { padding-bottom: 14px; margin-bottom: 14px; border-bottom: 1px solid var(--line); }
      .item:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: 0; }
      .cwd-select { width: 100%; }
      .cwd-custom[hidden] { display: none; }
      .cwd-hint { font-size: 0.9rem; }
      @media (max-width: 720px) {
        header, main { padding: 18px; }
        .panel { min-height: 0; }
        .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }
    </style>
  </head>
  <body>
    <header>
      <h1>personal-agent / codex runner</h1>
      <p>UI -> draft -> confirm cwd -> launch codex -> result.</p>
      <div class="row">
        <button id="refresh-status" type="button" class="secondary">Refresh</button>
        <span id="refresh-state" class="muted">Manual refresh</span>
      </div>
      <div id="summary" class="summary-grid" aria-live="polite"></div>
    </header>
    <main>
      <section class="grid">
        <div class="panel">
          <h2>New Task</h2>
          <form id="intake-form">
            <textarea id="intake-input" placeholder="Describe the code task."></textarea>
            <button type="submit">Create draft</button>
          </form>
          <p id="intake-status" class="muted"></p>
        </div>
        <div class="panel">
          <h2>Active Runs</h2>
          <div id="active-runs" class="list-slot"></div>
        </div>
      </section>
      <section class="grid" style="margin-top: 16px;">
        <div class="panel">
          <h2>Drafts</h2>
          <div id="drafts" class="list-slot"></div>
        </div>
        <div class="panel">
          <h2>Recent Results</h2>
          <div id="results" class="list-slot"></div>
        </div>
        <div class="panel">
          <h2>Failed Runs</h2>
          <div id="failed" class="list-slot"></div>
        </div>
      </section>
    </main>
    <script>
      let cwdOptions = [];

      function escapeHtml(value) {
        return String(value ?? '')
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#39;');
      }
      function normalizePath(value) {
        return String(value ?? '').trim();
      }
      function renderList(id, items, template, emptyText) {
        const target = document.getElementById(id);
        if (!items.length) {
          target.innerHTML = `<div class="empty-state"><p class="muted">${emptyText}</p></div>`;
          return;
        }
        target.innerHTML = items.map(template).join('');
      }
      function renderSummary(summary) {
        const metrics = [
          ['drafts', summary.draft_count],
          ['running', summary.running_count],
          ['failed', summary.failed_count],
          ['results', summary.result_count],
        ];
        document.getElementById('summary').innerHTML = metrics.map(([label, value]) => `
          <div class="summary-card">
            <strong>${escapeHtml(value)}</strong>
            <span class="muted">${escapeHtml(label)}</span>
          </div>
        `).join('');
      }
      async function loadStatus() {
        document.getElementById('refresh-state').textContent = 'Refreshing...';
        const response = await fetch('/api/status');
        const payload = await response.json();
        cwdOptions = payload.cwd_options || [];
        renderList('drafts', payload.draft_tasks || [], draftTemplate, 'No drafts.');
        renderList('active-runs', payload.active_runs || [], activeTemplate, 'No active runs.');
        renderList('results', payload.recent_results || [], resultTemplate, 'No results yet.');
        renderList('failed', payload.failed_tasks || [], failedTemplate, 'No failed runs.');
        renderSummary(payload.summary);
        bindStartForms();
        document.getElementById('refresh-state').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      }
      function draftTemplate(task) {
        const currentCwd = normalizePath(task.cwd || '');
        const suggestedName = normalizePath(task.execution?.suggested_repo_name || '');
        const matchingOption = cwdOptions.find(option => normalizePath(option.path) === currentCwd);
        const includeCurrent = currentCwd && !matchingOption;
        const selectOptions = includeCurrent
          ? [{ name: suggestedName || currentCwd.split('/').filter(Boolean).pop() || 'Current path', path: currentCwd, source: 'current' }, ...cwdOptions]
          : cwdOptions;
        const selectedValue = matchingOption ? currentCwd : (includeCurrent ? currentCwd : '__custom__');
        const customValue = matchingOption || includeCurrent ? '' : currentCwd;
        const suggestionLabel = matchingOption
          ? `${matchingOption.name} · ${matchingOption.path}`
          : (suggestedName ? `${suggestedName} · ${currentCwd}` : currentCwd);
        return `
          <div class="item">
            <a href="/tasks/${encodeURIComponent(task.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(task.title)}</strong></a>
            <div class="meta">${escapeHtml(task.id)} / ${escapeHtml(task.permission_mode)}</div>
            <form class="start-form" data-task-id="${escapeHtml(task.id)}">
              <label>Workspace</label>
              <select name="cwd_select" class="cwd-select">
                ${selectOptions.map(option => `
                  <option value="${escapeHtml(option.path)}" ${normalizePath(option.path) === selectedValue ? 'selected' : ''}>
                    ${escapeHtml(option.name)} (${escapeHtml(option.source)})
                  </option>
                `).join('')}
                <option value="__custom__" ${selectedValue === '__custom__' ? 'selected' : ''}>Custom path</option>
              </select>
              <input name="cwd_custom" class="cwd-custom" value="${escapeHtml(customValue)}" placeholder="/Users/sebas/Code/..." ${selectedValue === '__custom__' ? '' : 'hidden'} />
              <div class="meta cwd-hint">Suggested: ${escapeHtml(suggestionLabel)}</div>
              <label>Prompt</label>
              <textarea name="prompt">${escapeHtml(task.execution?.prompt_preview || '')}</textarea>
              <button type="submit">OK + launch</button>
            </form>
          </div>
        `;
      }
      function activeTemplate(task) {
        return `
          <div class="item">
            <a href="/tasks/${encodeURIComponent(task.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(task.title)}</strong></a>
            <div class="meta">${escapeHtml(task.id)} / run ${escapeHtml(task.latest_run?.id || 'n/a')}</div>
            <div class="meta">cwd: ${escapeHtml(task.cwd || '')}</div>
            <div class="meta">status: ${escapeHtml(task.latest_run?.status || task.status)}</div>
          </div>
        `;
      }
      function failedTemplate(task) {
        return `
          <div class="item">
            <a href="/tasks/${encodeURIComponent(task.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(task.title)}</strong></a>
            <div class="meta">${escapeHtml(task.id)} / ${escapeHtml(task.latest_run?.status || task.status)}</div>
            <div class="meta">cwd: ${escapeHtml(task.cwd || '')}</div>
          </div>
        `;
      }
      function resultTemplate(item) {
        return `
          <div class="item">
            <a href="/artifacts/${encodeURIComponent(item.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(item.title)}</strong></a>
            <div class="meta">${escapeHtml(item.task_title)} / ${escapeHtml(item.task_status)}</div>
          </div>
        `;
      }
      function bindStartForms() {
        document.querySelectorAll('.start-form').forEach(form => {
          const select = form.querySelector('select[name="cwd_select"]');
          const customInput = form.querySelector('input[name="cwd_custom"]');
          const syncCwdMode = () => {
            const isCustom = select.value === '__custom__';
            customInput.hidden = !isCustom;
          };
          select.addEventListener('change', syncCwdMode);
          syncCwdMode();
          form.addEventListener('submit', async event => {
            event.preventDefault();
            const taskId = form.getAttribute('data-task-id');
            const cwd = select.value === '__custom__' ? customInput.value : select.value;
            const prompt = form.querySelector('textarea[name="prompt"]').value;
            const response = await fetch(`/api/tasks/${taskId}/start`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ cwd, prompt })
            });
            if (!response.ok) {
              const payload = await response.text();
              alert(payload);
              return;
            }
            await loadStatus();
          }, { once: true });
        });
      }
      document.getElementById('intake-form').addEventListener('submit', async event => {
        event.preventDefault();
        const input = document.getElementById('intake-input').value.trim();
        if (!input) return;
        const response = await fetch('/api/intake', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input })
        });
        const payload = await response.json();
        document.getElementById('intake-status').textContent = `Created draft ${payload.task.id}`;
        document.getElementById('intake-input').value = '';
        await loadStatus();
      });
      document.getElementById('refresh-status').addEventListener('click', async () => {
        await loadStatus();
      });
      loadStatus();
    </script>
  </body>
</html>
"""


class PersonalAgentHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], runtime: PersonalAgentRuntime) -> None:
        super().__init__(server_address, PersonalAgentHandler)
        self.runtime = runtime


class PersonalAgentHandler(BaseHTTPRequestHandler):
    server: PersonalAgentHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(HTML_PAGE)
            return
        if parsed.path == "/api/status":
            self._send_json(self.server.runtime.dashboard_snapshot())
            return
        if parsed.path.startswith("/api/tasks/"):
            task_id = parsed.path.split("/")[3]
            self._send_json(self.server.runtime.task_bundle(task_id))
            return
        if parsed.path.startswith("/api/artifacts/"):
            artifact_id = parsed.path.split("/")[3]
            self._send_json(self.server.runtime.service.get_artifact(artifact_id))
            return
        if parsed.path.startswith("/tasks/"):
            task_id = parsed.path.split("/")[2]
            self._send_html(self._task_page(self.server.runtime.task_bundle(task_id)))
            return
        if parsed.path.startswith("/artifacts/"):
            artifact_id = parsed.path.split("/")[2]
            self._send_html(self._artifact_page(self.server.runtime.service.get_artifact(artifact_id)))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._json_body()
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON body")
            return
        if parsed.path == "/api/intake":
            input_text = payload.get("input")
            if not isinstance(input_text, str) or not input_text.strip():
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing or invalid 'input'")
                return
            result = self.server.runtime.intake(input_text)
            self._send_json({"task": result.task, "memory_context": result.memory_context}, status=HTTPStatus.CREATED)
            return
        if parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/start"):
            task_id = parsed.path.split("/")[3]
            cwd = payload.get("cwd")
            prompt = payload.get("prompt")
            if not isinstance(cwd, str) or not cwd.strip():
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing or invalid 'cwd'")
                return
            if prompt is not None and not isinstance(prompt, str):
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid 'prompt'")
                return
            try:
                self._send_json(self.server.runtime.start_task(task_id, cwd, prompt))
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, f"Task not found: {task_id}")
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _artifact_page(self, artifact: dict[str, Any]) -> str:
        title = self._escape_html(str(artifact["title"]))
        task_id = self._escape_html(str(artifact["task_id"]))
        artifact_id = self._escape_html(str(artifact["id"]))
        artifact_type = self._escape_html(str(artifact["artifact_type"]))
        content = self._escape_html(str(artifact["content"]))
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      body {{ margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: #f5f1ea; color: #1f1a16; }}
      main {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
      .meta {{ color: #6c655d; margin-bottom: 12px; }}
      .artifact-body {{ white-space: pre-wrap; overflow-wrap: anywhere; background: white; border: 1px solid #dccdb9; border-radius: 18px; padding: 18px; }}
      .artifact-rendered pre {{ white-space: pre-wrap; background: #f7f1e8; border: 1px solid #dccdb9; border-radius: 12px; padding: 12px; overflow-x: auto; }}
      .artifact-rendered code {{ background: #f7f1e8; padding: 1px 4px; border-radius: 6px; }}
      .artifact-rendered a {{ font-size: 0.8em; }}
      .artifact-rendered a + a {{ margin-left: 0.3em; }}
    </style>
  </head>
  <body>
    <main>
      <p><a href="/">Back to dashboard</a></p>
      <h1>{title}</h1>
      <div class="meta">artifact: {artifact_id}</div>
      <div class="meta">task: {task_id}</div>
      <div class="meta">type: {artifact_type}</div>
      <div class="artifact-rendered">{self._render_markdown(str(artifact["content"]))}</div>
      <details>
        <summary>Raw markdown</summary>
        <div class="artifact-body">{content}</div>
      </details>
    </main>
  </body>
</html>"""

    def _task_page(self, bundle: dict[str, Any]) -> str:
        task = bundle["task"]
        execution = task.get("execution", {})
        latest_run = bundle.get("latest_run")
        artifact = bundle.get("latest_artifact")
        run_block = (
            f"<div class=\"meta\">run: {self._escape_html(str(latest_run['id']))} / {self._escape_html(str(latest_run['status']))}</div>"
            if latest_run
            else "<div class=\"meta\">run: none</div>"
        )
        artifact_block = (
            f"<div class=\"meta\">artifact: <a href=\"/artifacts/{self._escape_html(str(artifact['id']))}\">{self._escape_html(str(artifact['title']))}</a></div>"
            if artifact
            else "<div class=\"meta\">artifact: none</div>"
        )
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{self._escape_html(str(task['title']))}</title>
    <style>
      body {{ margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: #f5f1ea; color: #1f1a16; }}
      main {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
      .panel {{ background: white; border: 1px solid #dccdb9; border-radius: 18px; padding: 18px; margin-bottom: 16px; }}
      .meta {{ color: #6c655d; margin-bottom: 8px; overflow-wrap: anywhere; }}
      pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f1e8; border: 1px solid #dccdb9; border-radius: 12px; padding: 12px; }}
    </style>
  </head>
  <body>
    <main>
      <p><a href="/">Back to dashboard</a></p>
      <div class="panel">
        <h1>{self._escape_html(str(task['title']))}</h1>
        <div class="meta">task: {self._escape_html(str(task['id']))}</div>
        <div class="meta">status: {self._escape_html(str(task['status']))}</div>
        <div class="meta">cwd: {self._escape_html(str(execution.get('cwd') or execution.get('suggested_cwd') or ''))}</div>
        <div class="meta">permission: {self._escape_html(str(task.get('permission_mode') or 'danger-full-access'))}</div>
        {run_block}
        {artifact_block}
      </div>
      <div class="panel">
        <h2>Intent</h2>
        <pre>{self._escape_html(str(task['intent']))}</pre>
      </div>
      <div class="panel">
        <h2>Prompt</h2>
        <pre>{self._escape_html(str(execution.get('prompt_preview') or ''))}</pre>
      </div>
    </main>
  </body>
</html>"""

    def _escape_html(self, value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def _render_markdown(self, content: str, base_path: str | None = None) -> str:
        if not content.strip():
            return "<p class=\"muted\">Empty artifact.</p>"
        chunks: list[str] = []
        paragraph: list[str] = []
        list_items: list[tuple[str, str | None]] = []
        code_lines: list[str] = []
        in_code_block = False
        source_refs = self._collect_source_refs(content)
        in_sources_section = False

        def flush_paragraph() -> None:
            nonlocal paragraph
            if not paragraph:
                return
            chunks.append(f"<p>{self._render_inline_markdown(' '.join(paragraph))}</p>")
            paragraph = []

        def flush_list() -> None:
            nonlocal list_items
            if not list_items:
                return
            rendered_items: list[str] = []
            for item, item_id in list_items:
                id_attr = f' id="{item_id}"' if item_id else ""
                rendered_items.append(
                    f"<li{id_attr}>{self._render_inline_markdown(item, base_path, source_refs)}</li>"
                )
            chunks.append("<ul>" + "".join(rendered_items) + "</ul>")
            list_items = []

        def flush_code() -> None:
            nonlocal code_lines
            if not code_lines:
                return
            chunks.append("<pre><code>" + self._escape_html("\n".join(code_lines)) + "</code></pre>")
            code_lines = []

        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if line.startswith("```"):
                flush_paragraph()
                flush_list()
                if in_code_block:
                    flush_code()
                    in_code_block = False
                else:
                    in_code_block = True
                continue
            if in_code_block:
                code_lines.append(line)
                continue
            if not line.strip():
                flush_paragraph()
                flush_list()
                continue
            if line.startswith("#"):
                flush_paragraph()
                flush_list()
                level = min(len(line) - len(line.lstrip("#")), 3)
                text = line[level:].strip()
                in_sources_section = self._is_sources_heading(text)
                chunks.append(f"<h{level + 1}>{self._render_inline_markdown(text, base_path, source_refs)}</h{level + 1}>")
                continue
            if line.startswith("- "):
                flush_paragraph()
                item = line[2:]
                item_id = self._source_ref_id(item) if in_sources_section else None
                list_items.append((item, item_id))
                continue
            flush_list()
            paragraph.append(line)

        flush_paragraph()
        flush_list()
        flush_code()
        return "".join(chunks)

    def _render_inline_markdown(
        self,
        value: str,
        base_path: str | None = None,
        source_refs: set[str] | None = None,
    ) -> str:
        value = self._escape_html(value)
        value = re.sub(
            r"\[([^\]]+)\]\(([^)\s]+)\)",
            lambda match: self._render_markdown_link(match, base_path, source_refs),
            value,
        )
        value = re.sub(
            r"\[(S\d+)\]",
            lambda match: self._render_source_ref_link(match.group(1), source_refs),
            value,
        )
        value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
        value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
        value = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", value)
        return value

    def _render_markdown_link(
        self,
        match: re.Match[str],
        base_path: str | None = None,
        source_refs: set[str] | None = None,
    ) -> str:
        label = self._render_inline_markdown(match.group(1), base_path, source_refs)
        href = self._sanitize_href(match.group(2), base_path)
        if not href:
            return match.group(0)
        if href.startswith("#") or self._is_internal_route(href):
            return f'<a href="{href}">{label}</a>'
        return f'<a href="{href}" target="_blank" rel="noreferrer">{label}</a>'

    def _is_internal_route(self, href: str) -> bool:
        return href == "/" or href.startswith(("/artifacts/", "/tasks/", "/api/"))

    def _collect_source_refs(self, content: str) -> set[str]:
        refs: set[str] = set()
        in_sources_section = False
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if line.startswith("#"):
                text = line.lstrip("#").strip()
                in_sources_section = self._is_sources_heading(text)
                continue
            if not in_sources_section:
                continue
            match = re.match(r"-\s+\[(S\d+)\]", line)
            if match:
                refs.add(match.group(1))
        return refs

    def _is_sources_heading(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return normalized in {"sources", "fuentes primarias", "fuentes primarias usadas"}

    def _source_ref_id(self, value: str) -> str | None:
        match = re.match(r"\[(S\d+)\]", value.strip())
        if not match:
            return None
        return f"ref-{match.group(1).lower()}"

    def _render_source_ref_link(self, ref: str, source_refs: set[str] | None = None) -> str:
        if source_refs and ref in source_refs:
            href = f"#ref-{ref.lower()}"
            return f'<a href="{href}">[{ref}]</a>'
        return f"[{ref}]"

    def _sanitize_href(self, href: str, base_path: str | None = None) -> str:
        candidate = href.strip()
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https", "mailto"}:
            host = parsed.netloc.split(":")[0]
            if host in {"127.0.0.1", "localhost"} and parsed.path.startswith("/"):
                return parsed.path + (f"#{parsed.fragment}" if parsed.fragment else "")
            return candidate
        if candidate.startswith(("/", "./", "../", "#")):
            return candidate
        if self._looks_like_external_host(candidate):
            normalized = f"https://{candidate}"
            parsed = urlparse(normalized)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return normalized
        if self._looks_like_relative_href(candidate):
            return candidate
        return ""

    def _looks_like_external_host(self, href: str) -> bool:
        if re.search(r"\s", href):
            return False
        if "/" in href and href.startswith("/"):
            return False
        if ":" in href:
            return False
        host = href.split("/", 1)[0]
        return bool(re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", host))

    def _looks_like_relative_href(self, href: str) -> bool:
        if not href or re.search(r"\s", href):
            return False
        if href.startswith("//"):
            return False
        if ":" in href:
            return False
        return True


def run_server(host: str = "127.0.0.1", port: int = 8082, interval_seconds: float = 5.0) -> None:
    del interval_seconds
    runtime = PersonalAgentRuntime()
    server = PersonalAgentHTTPServer((host, port), runtime)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()
        server.server_close()
