# What Goes Where

## Default split

- `agents-database` = durable memory
- repo files = operating system

## Persist in DB

Use DB for things Ballbox should remember and retrieve later across sessions and agents:

- durable facts
- decisions
- constraints
- claims with evidence
- entity and repo descriptions
- durable tasks or open questions worth semantic retrieval
- short snapshots of relevant conversations

## Persist in files

Use files for things humans and agents need to read, edit, and run right now:

- cycle plans and reviews
- SOPs
- dashboard
- working TODOs
- project briefs
- raw signals
- longer notes in progress

## Rule of thumb

- if the question is "should we remember this later?" -> DB
- if the question is "should we work from this now?" -> file
- if both -> file for workflow, DB for durable distilled memory

## Ballbox examples

- "ATC is not formally associated with Ballbox" -> DB
- "C-01 plan" -> file
- "pilot club X objected to revenue share" -> file first in `signals/`
- if that objection changes a durable belief -> DB too
- "repo purpose for payment integration" -> DB, optionally linked from files
- "this week's top TODOs" -> file
