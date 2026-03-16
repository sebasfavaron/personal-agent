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
          <h2>Current Run</h2>
          <div id="current-run"></div>
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
      function escapeHtml(value) {
        return String(value ?? '')
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#39;');
      }
      function stateClass(value) {
        return ['running', 'ran_before', 'not_started'].includes(value) ? value : 'not_started';
      }
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
            <a class="artifact-link" href="/tasks/${encodeURIComponent(task.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(task.title)}</strong></a>
            <div class="task-id">${escapeHtml(task.id)}</div>
            <div class="pill ${stateClass(task.execution_state)}">${escapeHtml(taskStateLabel(task))}</div>
            <div class="meta">${escapeHtml(task.status)} / next: ${escapeHtml(task.next_action)}</div>
            <div class="meta">route: ${escapeHtml(task.route_summary.primary_agent)}${task.route_summary.planning_source ? ` / ${escapeHtml(task.route_summary.planning_source)}` : ''}</div>
            <div class="meta">subtasks: ${escapeHtml(task.open_subtask_count)}${task.latest_run ? ` / run: ${escapeHtml(task.latest_run.status)} / started: ${escapeHtml(task.last_run_started_at)}` : ''}</div>
          </li>
        `);
        renderCurrentRun(payload.current_run);
        renderBlocked(payload.blocked_tasks);
        renderList('deliverables', payload.recent_deliverables || [], artifact => `
          <li>
            <a class="artifact-link" href="/artifacts/${encodeURIComponent(artifact.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(artifact.title)}</strong></a>
            <div class="task-id">${escapeHtml(artifact.task_title)}</div>
            <div class="meta">${escapeHtml(artifact.task_id)} / ${escapeHtml(artifact.task_status)}</div>
          </li>
        `);
        renderList('handoffs', payload.pending_handoffs, handoff => `<li><strong>${escapeHtml(handoff.to_agent)}</strong><div class="task-id">${escapeHtml(handoff.task_id)}</div><div class="meta">${escapeHtml(handoff.status)} / ${escapeHtml(handoff.reason)}</div></li>`);
        renderApprovals(payload.pending_approvals);
        renderList('artifacts', payload.recent_artifacts.slice(0, 8), artifact => `
          <li>
            <a class="artifact-link" href="/artifacts/${encodeURIComponent(artifact.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(artifact.title)}</strong></a>
            <div class="task-id">${escapeHtml(artifact.task_id)}</div>
            <div class="meta">${escapeHtml(artifact.artifact_type)}${artifact.metadata?.classification ? ` / ${escapeHtml(artifact.metadata.classification)}` : ''}</div>
          </li>
        `);
        document.getElementById('summary').innerHTML = `
          <strong>${escapeHtml(payload.summary.active_task_count)}</strong> active /
          <strong>${escapeHtml(payload.summary.blocked_task_count)}</strong> blocked /
          <strong>${escapeHtml(payload.summary.pending_approval_count)}</strong> approvals /
          <strong>${escapeHtml(payload.summary.pending_handoff_count)}</strong> handoffs /
          <strong>${escapeHtml(payload.summary.running_task_count)}</strong> running /
          <strong>${escapeHtml(payload.summary.started_task_count)}</strong> started /
          <strong>${escapeHtml(payload.summary.queued_task_count)}</strong> not started
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
      function renderCurrentRun(item) {
        const target = document.getElementById('current-run');
        if (!item) {
          target.innerHTML = '<p class="muted">No active run.</p>';
          return;
        }
        target.innerHTML = `
          <p><a class="artifact-link" href="/tasks/${encodeURIComponent(item.task_id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(item.task_title)}</strong></a></p>
          <div class="task-id">${escapeHtml(item.task_id)}</div>
          <div class="meta">task: ${escapeHtml(item.task_status)} / run: ${escapeHtml(item.run_status)}</div>
          <div class="meta">started: ${escapeHtml(item.started_at)}</div>
          <div class="meta">next: ${escapeHtml(item.next_action)}</div>
          <div class="meta">open subtasks: ${escapeHtml(item.open_subtask_count)}</div>
        `;
      }
      function renderBlocked(items) {
        const target = document.getElementById('blocked');
        if (!items.length) {
          target.innerHTML = '<p class="muted">No blockers.</p>';
          return;
        }
        target.innerHTML = items.map(task => `
          <div style="margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid var(--line);">
            <a class="artifact-link" href="/tasks/${encodeURIComponent(task.id)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(task.title)}</strong></a>
            <div class="task-id">${escapeHtml(task.id)}</div>
            <div class="pill ${stateClass(task.execution_state)}">${escapeHtml(taskStateLabel(task))}</div>
            <p class="warn">${escapeHtml(task.blocked_reason || 'Blocked')}</p>
            <div class="meta">next: ${escapeHtml(task.next_action)}${task.latest_run ? ` / run: ${escapeHtml(task.latest_run.status)} / started: ${escapeHtml(task.last_run_started_at)}` : ''}</div>
            <form data-task-id="${escapeHtml(task.id)}" class="blocker-form">
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
            <strong>${escapeHtml(approval.kind)}</strong>
            <div class="task-id">${escapeHtml(approval.id)}</div>
            <div class="meta">${escapeHtml(approval.task_id)} / ${escapeHtml(approval.risk_level)}</div>
            <form data-approval-id="${escapeHtml(approval.id)}" data-status="approved" class="approval-form">
              <textarea rows="2" placeholder="Optional approval note"></textarea>
              <button type="submit">Approve + resume</button>
            </form>
            <form data-approval-id="${escapeHtml(approval.id)}" data-status="rejected" class="approval-form" style="margin-top: 8px;">
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
            artifact = self.server.runtime.service.get_artifact(artifact_id)
            self._send_html(self._artifact_page(artifact))
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
            try:
                result = self.server.runtime.intake(input_text)
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
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
            response_text = payload.get("response")
            if not isinstance(response_text, str) or not response_text.strip():
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing or invalid 'response'")
                return
            try:
                self._send_json(self.server.runtime.respond_to_blocker(task_id, response_text))
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, f"Task not found: {task_id}")
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if parsed.path.startswith("/api/approvals/") and parsed.path.endswith("/resolve"):
            approval_id = parsed.path.split("/")[3]
            status = payload.get("status")
            note = payload.get("note", "")
            if not isinstance(status, str) or status.strip().lower() not in {"approved", "rejected"}:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing or invalid 'status'")
                return
            if note is None:
                note = ""
            if not isinstance(note, str):
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid 'note'")
                return
            try:
                self._send_json(self.server.runtime.resolve_approval(approval_id, status, note))
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, f"Approval not found: {approval_id}")
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

    def _task_page(self, bundle: dict[str, Any]) -> str:
        task = bundle["task"]
        task_id = self._escape_html(str(task["id"]))
        title = self._escape_html(str(task["title"]))
        blocked_reason = self._escape_html(str(task.get("blocked_reason") or ""))
        summary_rows = [
            f"<div class=\"meta\">status: {self._escape_html(str(task['status']))}</div>",
            f"<div class=\"meta\">next: {self._escape_html(str(task['next_action']))}</div>",
            f"<div class=\"meta\">open subtasks: {self._escape_html(str(task['open_subtask_count']))}</div>",
        ]
        if blocked_reason:
            summary_rows.append(f"<div class=\"meta warn\">blocked: {blocked_reason}</div>")
        children = self._list_section(
            "Subtasks",
            bundle["children"],
            lambda item: (
                f"<li><strong>{self._escape_html(str(item['title']))}</strong>"
                f"<div class=\"task-id\">{self._escape_html(str(item['id']))}</div>"
                f"<div class=\"meta\">{self._escape_html(str(item['status']))}</div></li>"
            ),
        )
        runs = self._list_section(
            "Runs",
            bundle["runs"],
            lambda item: (
                f"<li><strong>{self._escape_html(str(item['status']))}</strong>"
                f"<div class=\"task-id\">{self._escape_html(str(item['id']))}</div>"
                f"<div class=\"meta\">started: {self._escape_html(str(item['started_at']))}</div>"
                f"<div class=\"meta\">summary: {self._escape_html(str(item.get('result_summary') or ''))}</div></li>"
            ),
        )
        handoffs = self._list_section(
            "Handoffs",
            bundle["handoffs"],
            lambda item: (
                f"<li><strong>{self._escape_html(str(item['to_agent']))}</strong>"
                f"<div class=\"task-id\">{self._escape_html(str(item['id']))}</div>"
                f"<div class=\"meta\">{self._escape_html(str(item['status']))} / {self._escape_html(str(item['reason']))}</div></li>"
            ),
        )
        approvals = self._list_section(
            "Approvals",
            bundle["approvals"],
            lambda item: (
                f"<li><strong>{self._escape_html(str(item['kind']))}</strong>"
                f"<div class=\"task-id\">{self._escape_html(str(item['id']))}</div>"
                f"<div class=\"meta\">{self._escape_html(str(item['status']))}</div></li>"
            ),
        )
        artifacts = self._list_section(
            "Artifacts",
            bundle["artifacts"],
            lambda item: (
                f"<li><a class=\"artifact-link\" href=\"/artifacts/{self._escape_html(str(item['id']))}\" target=\"_blank\" rel=\"noreferrer\"><strong>{self._escape_html(str(item['title']))}</strong></a>"
                f"<div class=\"task-id\">{self._escape_html(str(item['id']))}</div>"
                f"<div class=\"meta\">{self._escape_html(str(item['artifact_type']))}</div></li>"
            ),
        )
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
        --warn: #a23d2f;
        --info: #1c5d99;
      }}
      body {{ margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: linear-gradient(180deg, #efe7dc, #f8f4ee); color: var(--ink); }}
      a {{ color: var(--info); text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
      .page {{ max-width: 1080px; margin: 0 auto; padding: 24px; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
      .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px; }}
      .meta {{ color: var(--muted); margin-bottom: 8px; overflow-wrap: anywhere; }}
      .warn {{ color: var(--warn); }}
      ul {{ padding-left: 18px; margin: 0; }}
      li {{ margin-bottom: 10px; overflow-wrap: anywhere; }}
      .task-id {{ color: var(--muted); font-size: 0.86rem; }}
    </style>
  </head>
  <body>
    <main class="page">
      <p><a href="/">Back to dashboard</a></p>
      <h1>{title}</h1>
      <div class="task-id">{task_id}</div>
      {''.join(summary_rows)}
      <section class="grid">
        <div class="panel">{children}</div>
        <div class="panel">{runs}</div>
        <div class="panel">{handoffs}</div>
        <div class="panel">{approvals}</div>
        <div class="panel" style="grid-column: 1 / -1;">{artifacts}</div>
      </section>
    </main>
  </body>
</html>"""

    def _list_section(self, title: str, items: list[dict[str, Any]], renderer: Any) -> str:
        if not items:
            return f"<h2>{self._escape_html(title)}</h2><p class=\"muted\">None.</p>"
        return f"<h2>{self._escape_html(title)}</h2><ul>{''.join(renderer(item) for item in items)}</ul>"

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
