# Agent Harness

Utilities for running external agent/model experiments without polluting the current session output.

## `opencode_clean_run.py`

Runs `opencode run --format json`, saves raw stdout/stderr logs, and prints only assistant text.

Supports reusable preambles so you can apply generic task guardrails without rewriting them into every prompt.

Example:

```bash
python3 "/Users/sebas/personal-agent/agent-harness/opencode_clean_run.py" \
  --model "opencode/minimax-m2.5-free" \
  --dir "/Users/sebas/Downloads" \
  --preamble-file "/Users/sebas/personal-agent/agent-harness/preambles/generic-verified-task.md" \
  "Lee y extrae la estructura del cuestionario desde este archivo local en el directorio actual: Encuesta a Entrenadores_ Desafíos y Prioridades en la Gestión de Clases.html"
```

Logs are stored under `/Users/sebas/personal-agent/agent-harness/logs/`.

## Preambles

- `preambles/generic-verified-task.md`: generic reliability guardrails for extraction, analysis, debugging, and other tasks.
- `preambles/structured-artifact-analysis.md`: prefer embedded structured data and programmatic parsing before heuristic scraping.

Use `--preamble-file` to prepend one of these to the task prompt.
