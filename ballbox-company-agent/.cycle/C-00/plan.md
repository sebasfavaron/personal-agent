# C-00 Plan

## Theme

Make Ballbox state agent-readable.

## Main effort

- set up Ballbox filesystem operating system
- centralize core facts, constraints, and current unknowns
- preserve shared-memory access

## Hypotheses

- if Ballbox state is centralized in files, agents can reason with less drift
- if unknowns are explicit, research and execution quality improves
- if the weekly loop is standardized, decisions become easier to trace

## Planned outputs

- root dashboard
- Ballbox constitution in `.self/`
- active project map
- SOP set for daily and cycle loops
- working CLI for shared-memory search

## Risks

- memory write access may be blocked by environment permissions
- current Ballbox commercial facts still incomplete

## Budget

- highest time: company OS and commercial clarity
- medium time: pilot ops and product surface mapping
- low time: polish
