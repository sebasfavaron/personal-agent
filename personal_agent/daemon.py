from __future__ import annotations

import json
import re
import threading
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
    <title>personal-agent v1</title>
    <style>
      :root {
        --bg: #f4f0e8;
        --panel: #fffaf2;
        --ink: #1e1a16;
        --muted: #6f655c;
        --line: #d8c8b3;
        --accent: #0b6e4f;
        --warn: #a23d2f;
        --info: #1c5d99;
      }
      body { margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: linear-gradient(180deg, #efe7dc, #f8f4ee); color: var(--ink); }
      header, main { max-width: 1200px; margin: 0 auto; padding: 24px; }
      header h1 { margin: 0 0 8px; font-size: 2.2rem; }
      header p { margin: 0; color: var(--muted); }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
      .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 12px 30px rgba(56, 40, 22, 0.08); }
      .panel, .panel * { min-width: 0; }
      h2 { margin-top: 0; font-size: 1.05rem; letter-spacing: 0.04em; text-transform: uppercase; }
      ul { padding-left: 18px; margin: 0; }
      li { margin-bottom: 10px; }
      li, strong, .task-id, .meta, p { overflow-wrap: anywhere; word-break: break-word; }
      code { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.9em; }
      .muted { color: var(--muted); }
      .warn { color: var(--warn); }
      form { display: flex; gap: 8px; flex-direction: column; }
      input, textarea, button { font: inherit; }
      textarea, input { width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid var(--line); padding: 10px 12px; background: white; }
      button { border: 0; background: var(--accent); color: white; padding: 10px 14px; border-radius: 999px; width: fit-content; cursor: pointer; }
      .task-id { color: var(--muted); font-size: 0.86rem; }
      .meta { color: var(--muted); font-size: 0.86rem; }
      .pill { display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 0.78rem; border: 1px solid var(--line); background: white; margin-top: 6px; }
      .pill.running { border-color: var(--accent); color: var(--accent); }
      .pill.ran_before { border-color: var(--info); color: var(--info); }
      .pill.not_started { border-color: var(--muted); color: var(--muted); }
      a { color: var(--info); text-decoration: none; }
      a:hover { text-decoration: underline; }
      .artifact-link { display: inline-block; max-width: 100%; }
      .artifact-page { max-width: 980px; margin: 0 auto; padding: 24px; }
      .artifact-body { white-space: pre-wrap; overflow-wrap: anywhere; background: white; border: 1px solid var(--line); border-radius: 18px; padding: 18px; }
      .artifact-rendered { overflow-wrap: anywhere; background: white; border: 1px solid var(--line); border-radius: 18px; padding: 18px; margin-bottom: 16px; }
      .artifact-rendered pre { white-space: pre-wrap; background: #f7f1e8; border: 1px solid var(--line); border-radius: 12px; padding: 12px; overflow-x: auto; }
      .artifact-rendered code { background: #f7f1e8; padding: 1px 4px; border-radius: 6px; }
    </style>
  </head>
  <body>
    <header>
      <h1>personal-agent / v1</h1>
      <p>Front door, event worker, blocker inbox, shared-memory orchestration.</p>
      <p id="summary" class="muted"></p>
    </header>
    <main>
      <section class="grid">
        <div class="panel">
          <h2>New Intake</h2>
          <form id="intake-form">
            <textarea id="intake-input" rows="5" placeholder="Describe the task you want the system to take over."></textarea>
            <button type="submit">Create task</button>
          </form>
          <p id="intake-status" class="muted"></p>
        </div>
        <div class="panel">
          <h2>Blocked Tasks</h2>
          <div id="blocked"></div>
        </div>
      </section>
      <section class="grid" style="margin-top: 16px;">
        <div class="panel"><h2>Active Tasks</h2><div id="active"></div></div>
        <div class="panel"><h2>Recent Deliverables</h2><div id="deliverables"></div></div>
        <div class="panel"><h2>Pending Handoffs</h2><div id="handoffs"></div></div>
        <div class="panel"><h2>Pending Approvals</h2><div id="approvals"></div></div>
        <div class="panel"><h2>Recent Artifacts</h2><div id="artifacts"></div></div>
      </section>
    </main>
    <script>
      function taskStateLabel(task) {
        if (task.execution_state === 'running') return 'running now';
        if (task.execution_state === 'ran_before') return 'ran before';
        return 'not started';
      }
      async function loadStatus() {
        const response = await fetch('/api/status');
        const payload = await response.json();
        renderList('active', payload.active_tasks, task => `
          <li>
            <strong>${task.title}</strong>
            <div class="task-id">${task.id}</div>
            <div class="pill ${task.execution_state}">${taskStateLabel(task)}</div>
            <div class="meta">${task.status} / next: ${task.next_action}</div>
            <div class="meta">route: ${task.route_summary.primary_agent}${task.route_summary.planning_source ? ` / ${task.route_summary.planning_source}` : ''}</div>
            <div class="meta">subtasks: ${task.open_subtask_count}${task.latest_run ? ` / run: ${task.latest_run.status} / started: ${task.last_run_started_at}` : ''}</div>
          </li>
        `);
        renderBlocked(payload.blocked_tasks);
        renderList('deliverables', payload.recent_deliverables || [], artifact => `
          <li>
            <a class="artifact-link" href="/artifacts/${artifact.id}" target="_blank" rel="noreferrer"><strong>${artifact.title}</strong></a>
            <div class="task-id">${artifact.task_title}</div>
            <div class="meta">${artifact.task_id} / ${artifact.task_status}</div>
          </li>
        `);
        renderList('handoffs', payload.pending_handoffs, handoff => `<li><strong>${handoff.to_agent}</strong><div class="task-id">${handoff.task_id}</div><div class="meta">${handoff.reason}</div></li>`);
        renderApprovals(payload.pending_approvals);
        renderList('artifacts', payload.recent_artifacts.slice(0, 8), artifact => `
          <li>
            <a class="artifact-link" href="/artifacts/${artifact.id}" target="_blank" rel="noreferrer"><strong>${artifact.title}</strong></a>
            <div class="task-id">${artifact.task_id}</div>
            <div class="meta">${artifact.artifact_type}</div>
          </li>
        `);
        document.getElementById('summary').innerHTML = `
          <strong>${payload.summary.active_task_count}</strong> active /
          <strong>${payload.summary.blocked_task_count}</strong> blocked /
          <strong>${payload.summary.pending_approval_count}</strong> approvals /
          <strong>${payload.summary.pending_handoff_count}</strong> handoffs /
          <strong>${payload.summary.running_task_count}</strong> running /
          <strong>${payload.summary.started_task_count}</strong> started /
          <strong>${payload.summary.queued_task_count}</strong> not started
        `;
      }
      function renderList(id, items, template) {
        const target = document.getElementById(id);
        if (!items.length) {
          target.innerHTML = '<p class="muted">None.</p>';
          return;
        }
        target.innerHTML = `<ul>${items.map(template).join('')}</ul>`;
      }
      function renderBlocked(items) {
        const target = document.getElementById('blocked');
        if (!items.length) {
          target.innerHTML = '<p class="muted">No blockers.</p>';
          return;
        }
        target.innerHTML = items.map(task => `
          <div style="margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid var(--line);">
            <strong>${task.title}</strong>
            <div class="task-id">${task.id}</div>
            <div class="pill ${task.execution_state}">${taskStateLabel(task)}</div>
            <p class="warn">${task.blocked_reason || 'Blocked'}</p>
            <div class="meta">next: ${task.next_action}${task.latest_run ? ` / run: ${task.latest_run.status} / started: ${task.last_run_started_at}` : ''}</div>
            <form data-task-id="${task.id}" class="blocker-form">
              <textarea rows="3" placeholder="Add the missing context to continue"></textarea>
              <button type="submit">Resolve blocker</button>
            </form>
          </div>
        `).join('');
        document.querySelectorAll('.blocker-form').forEach(form => {
          form.addEventListener('submit', async event => {
            event.preventDefault();
            const taskId = form.getAttribute('data-task-id');
            const response = form.querySelector('textarea').value;
            await fetch(`/api/tasks/${taskId}/blocker-response`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ response })
            });
            await loadStatus();
          });
        });
      }
      function renderApprovals(items) {
        const target = document.getElementById('approvals');
        if (!items.length) {
          target.innerHTML = '<p class="muted">None.</p>';
          return;
        }
        target.innerHTML = items.map(approval => `
          <div style="margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid var(--line);">
            <strong>${approval.kind}</strong>
            <div class="task-id">${approval.id}</div>
            <div class="meta">${approval.task_id} / ${approval.risk_level}</div>
            <form data-approval-id="${approval.id}" data-status="approved" class="approval-form">
              <textarea rows="2" placeholder="Optional approval note"></textarea>
              <button type="submit">Approve + resume</button>
            </form>
            <form data-approval-id="${approval.id}" data-status="rejected" class="approval-form" style="margin-top: 8px;">
              <textarea rows="2" placeholder="Reason for rejection"></textarea>
              <button type="submit" style="background: var(--warn);">Reject</button>
            </form>
          </div>
        `).join('');
        document.querySelectorAll('.approval-form').forEach(form => {
          form.addEventListener('submit', async event => {
            event.preventDefault();
            const approvalId = form.getAttribute('data-approval-id');
            const status = form.getAttribute('data-status');
            const note = form.querySelector('textarea').value;
            await fetch(`/api/approvals/${approvalId}/resolve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ status, note })
            });
            await loadStatus();
          });
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
        document.getElementById('intake-status').textContent = `Created ${payload.task.id}`;
        document.getElementById('intake-input').value = '';
        await loadStatus();
      });
      loadStatus();
      setInterval(loadStatus, 5000);
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
        if parsed.path.startswith("/api/artifacts/"):
            artifact_id = parsed.path.split("/")[3]
            self._send_json(self.server.runtime.service.get_artifact(artifact_id))
            return
        if parsed.path.startswith("/artifacts/"):
            artifact_id = parsed.path.split("/")[2]
            artifact = self.server.runtime.service.get_artifact(artifact_id)
            self._send_html(self._artifact_page(artifact))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._json_body()
        if parsed.path == "/api/intake":
            result = self.server.runtime.intake(payload["input"])
            self._send_json(
                {
                    "task": result.task,
                    "subtasks": result.subtasks,
                    "artifacts": result.artifacts,
                    "handoff": result.handoff,
                },
                status=HTTPStatus.CREATED,
            )
            return
        if parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/blocker-response"):
            task_id = parsed.path.split("/")[3]
            self._send_json(self.server.runtime.respond_to_blocker(task_id, payload["response"]))
            return
        if parsed.path.startswith("/api/approvals/") and parsed.path.endswith("/resolve"):
            approval_id = parsed.path.split("/")[3]
            self._send_json(self.server.runtime.resolve_approval(approval_id, payload["status"], payload.get("note", "")))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

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
      :root {{
        --bg: #f4f0e8;
        --panel: #fffaf2;
        --ink: #1e1a16;
        --muted: #6f655c;
        --line: #d8c8b3;
        --info: #1c5d99;
      }}
      body {{ margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: linear-gradient(180deg, #efe7dc, #f8f4ee); color: var(--ink); }}
      a {{ color: var(--info); text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
      .artifact-page {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
      .artifact-body {{ white-space: pre-wrap; overflow-wrap: anywhere; background: white; border: 1px solid var(--line); border-radius: 18px; padding: 18px; }}
      .artifact-rendered {{ overflow-wrap: anywhere; background: white; border: 1px solid var(--line); border-radius: 18px; padding: 18px; margin-bottom: 16px; }}
      .artifact-rendered pre {{ white-space: pre-wrap; background: #f7f1e8; border: 1px solid var(--line); border-radius: 12px; padding: 12px; overflow-x: auto; }}
      .artifact-rendered code {{ background: #f7f1e8; padding: 1px 4px; border-radius: 6px; }}
      .meta {{ color: var(--muted); margin-bottom: 12px; }}
    </style>
  </head>
  <body>
    <main class="artifact-page">
      <p><a href="/">Back to dashboard</a></p>
      <h1>{title}</h1>
      <div class="meta">artifact: {artifact_id}</div>
      <div class="meta">task: {task_id}</div>
      <div class="meta">type: {artifact_type}</div>
      <div class="artifact-rendered">{self._render_markdown(str(artifact["content"]))}</div>
      <details>
        <summary>Raw markdown</summary>
        <div class="artifact-body" id="raw-markdown">{content}</div>
      </details>
    </main>
  </body>
</html>"""

    def _escape_html(self, value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _render_markdown(self, value: str) -> str:
        escaped = self._escape_html(value)
        parts = escaped.split("```")
        blocks: list[str] = []
        in_code = False
        for part in parts:
            if in_code:
                blocks.append(f"<pre><code>{part.strip()}</code></pre>")
            else:
                blocks.append(self._render_markdown_blocks(part))
            in_code = not in_code
        return "".join(blocks)

    def _render_markdown_blocks(self, value: str) -> str:
        lines = value.splitlines()
        chunks: list[str] = []
        paragraph: list[str] = []
        list_items: list[str] = []

        def flush_paragraph() -> None:
            if paragraph:
                chunks.append(f"<p>{self._render_inline_markdown(' '.join(paragraph).strip())}</p>")
                paragraph.clear()

        def flush_list() -> None:
            if list_items:
                chunks.append("<ul>" + "".join(f"<li>{self._render_inline_markdown(item)}</li>" for item in list_items) + "</ul>")
                list_items.clear()

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                flush_paragraph()
                flush_list()
                continue
            if line.startswith("### "):
                flush_paragraph()
                flush_list()
                chunks.append(f"<h3>{self._render_inline_markdown(line[4:])}</h3>")
                continue
            if line.startswith("## "):
                flush_paragraph()
                flush_list()
                chunks.append(f"<h2>{self._render_inline_markdown(line[3:])}</h2>")
                continue
            if line.startswith("# "):
                flush_paragraph()
                flush_list()
                chunks.append(f"<h1>{self._render_inline_markdown(line[2:])}</h1>")
                continue
            if line.startswith("- "):
                flush_paragraph()
                list_items.append(line[2:])
                continue
            flush_list()
            paragraph.append(line)

        flush_paragraph()
        flush_list()
        return "".join(chunks)

    def _render_inline_markdown(self, value: str) -> str:
        value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
        value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
        value = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", value)
        return value


def run_server(host: str = "127.0.0.1", port: int = 8082, interval_seconds: float = 5.0) -> None:
    runtime = PersonalAgentRuntime()
    worker = threading.Thread(target=runtime.serve_forever, kwargs={"interval_seconds": interval_seconds}, daemon=True)
    worker.start()
    server = PersonalAgentHTTPServer((host, port), runtime)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()
        server.server_close()
