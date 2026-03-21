# Parallel Work Modes

## Default
- prefer same branch + subagents
- one main agent integrates
- subagents get explicit file/module ownership
- good for fast iteration, small/medium scoped work, side quests, bounded tests/docs
- strongest fit: exploration, investigation, review, verification, and other non-write tasks

## Same Branch, Multiple Agents
- use only when write sets are clearly disjoint
- avoid shared hot files, shared infra, shared routing roots
- good when integration cost is low
- risk: silent conflicts, mixed diffs, harder debugging
- for write tasks, boundaries must be hard, not implied

## Worktrees
- use for larger features, refactors, risky spikes, alternative approaches
- better isolation
- easier rollback/abandon path
- slower loop; more setup cost

## Practical Rule
- same files or same hot path: worktree
- disjoint files with one clear integrator: same branch
- research, tests, docs, bounded implementation: subagents
- if the task does not involve writing, subagents are usually an easy win
- if the task does involve writing, be extremely explicit about ownership before starting

## Operating Pattern
- main agent:
  - owns architecture
  - owns integration
  - owns final checks
- subagents:
  - narrow task
  - disjoint write scope
  - short feedback loop
  - no reverting others

## Writing vs Non-Writing
- non-writing tasks:
  - best default for subagents
  - examples: codebase exploration, root-cause search, test strategy, verification, review, source gathering
  - low coordination cost
  - little downside beyond duplicated reading
- writing tasks:
  - use subagents only with explicit file ownership or module ownership
  - the main agent should avoid editing inside a delegated write scope while that subagent is active
  - if ownership is fuzzy, expect thrash, stale assumptions, and time lost debugging
  - if multiple writers may need the same file or flow, prefer a worktree instead

## Preferred Order
1. same branch + subagents + explicit ownership
2. worktrees for high-conflict or high-uncertainty work
3. multiple loose agents on one branch only if the domain split is very clean
