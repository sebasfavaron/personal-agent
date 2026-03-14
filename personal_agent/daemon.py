from __future__ import annotations

import json
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
      }
      body { margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: linear-gradient(180deg, #efe7dc, #f8f4ee); color: var(--ink); }
      header, main { max-width: 1200px; margin: 0 auto; padding: 24px; }
      header h1 { margin: 0 0 8px; font-size: 2.2rem; }
      header p { margin: 0; color: var(--muted); }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
      .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 12px 30px rgba(56, 40, 22, 0.08); }
      h2 { margin-top: 0; font-size: 1.05rem; letter-spacing: 0.04em; text-transform: uppercase; }
      ul { padding-left: 18px; margin: 0; }
      li { margin-bottom: 10px; }
      code { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.9em; }
      .muted { color: var(--muted); }
      .warn { color: var(--warn); }
      form { display: flex; gap: 8px; flex-direction: column; }
      input, textarea, button { font: inherit; }
      textarea, input { width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid var(--line); padding: 10px 12px; background: white; }
      button { border: 0; background: var(--accent); color: white; padding: 10px 14px; border-radius: 999px; width: fit-content; cursor: pointer; }
      .task-id { color: var(--muted); font-size: 0.86rem; }
      .meta { color: var(--muted); font-size: 0.86rem; }
    </style>
  </head>
  <body>
    <header>
      <h1>personal-agent / v1</h1>
      <p>Front door, event worker, blocker inbox, shared-memory orchestration.</p>
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
        <div class="panel"><h2>Pending Handoffs</h2><div id="handoffs"></div></div>
        <div class="panel"><h2>Pending Approvals</h2><div id="approvals"></div></div>
        <div class="panel"><h2>Recent Artifacts</h2><div id="artifacts"></div></div>
      </section>
    </main>
    <script>
      async function loadStatus() {
        const response = await fetch('/api/status');
        const payload = await response.json();
        renderList('active', payload.active_tasks, task => `<li><strong>${task.title}</strong><div class="task-id">${task.id}</div><div class="meta">${task.status}</div></li>`);
        renderBlocked(payload.blocked_tasks);
        renderList('handoffs', payload.pending_handoffs, handoff => `<li><strong>${handoff.to_agent}</strong><div class="task-id">${handoff.task_id}</div><div class="meta">${handoff.reason}</div></li>`);
        renderApprovals(payload.pending_approvals);
        renderList('artifacts', payload.recent_artifacts.slice(0, 8), artifact => `<li><strong>${artifact.title}</strong><div class="task-id">${artifact.task_id}</div><div class="meta">${artifact.artifact_type}</div></li>`);
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
            <p class="warn">${task.blocked_reason || 'Blocked'}</p>
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


def run_server(host: str = "127.0.0.1", port: int = 6666, interval_seconds: float = 5.0) -> None:
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
