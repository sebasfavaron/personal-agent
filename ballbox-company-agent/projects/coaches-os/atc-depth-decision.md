# ATC Depth Decision

## Purpose

- Decide what depth of ATC integration Ballbox needs for the first valuable loop.

## Options

### Option A - Read-only ATC

- Ballbox reads clubs, courts, availability, bookings, or related context
- Ballbox does not create/update/cancel bookings in ATC for v1

Pros:
- faster to ship
- lower integration risk
- easier to get initial access approved
- enough for some coordination, insight, and recommendation loops

Cons:
- less workflow closure
- manual handoff may remain
- weaker operational moat if Ballbox only informs but does not act

Best fit when:
- first wedge is coordination or recommendation-heavy
- write access is delayed or politically hard

### Option B - Read + write ATC

- Ballbox reads context and also creates/updates/cancels booking-side records

Pros:
- stronger workflow ownership
- better fit for reprogramming and scheduling wedges
- clearer moat if Ballbox becomes operationally embedded

Cons:
- slower
- more risk
- harder permissions/access conversation
- more edge cases and failure handling

Best fit when:
- first wedge is clearly scheduling/reprogramming
- ATC grants sufficient safe access

## Current recommendation

- default toward `read+write` for the product direction when the wedge is meant to be truly sellable and workflow-closing.
- use `read-only` only as a temporary technical phase if needed for prototyping or very early workflow learning.
- reason: Ballbox is likely much harder to sell if it only recommends actions but forces coaches to complete key operational steps elsewhere.

## Revisit trigger

- allow temporary `read-only` only if:
  - it helps validate a narrow workflow very quickly
  - Ballbox is explicitly testing before closing the loop
  - the team is clear that this is not the intended sellable end state
