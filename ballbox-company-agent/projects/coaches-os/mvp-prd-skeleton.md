# MVP PRD Skeleton

## Status

- stage: placeholder
- evidence level: do not finalize until interviews and first wedge decision are stronger

## Chosen wedge

- wedge: student-facing class discovery + request with ATC-backed class and court context
- user: student first; coach time-saving is the core rationale
- likely buyer: unresolved, with current rule that clubs/coordinators are acceptable payer fallback if coaches love the workflow
- why now:
  - it uses ATC public-read availability immediately
  - it removes repetitive coach coordination from the student side
  - it avoids dependence on ATC professor records by keeping coaches local to Ballbox

## Problem

- recurring workflow: students discover availability through fragmented conversations, while coaches absorb repetitive inbound coordination
- current workaround: WhatsApp chains, ad hoc slot proposals, club coordination, and manual follow-ups
- cost of failure: lost time for coaches, missed opportunities, slower conversion, and weaker student experience
- why existing tools fail: there is no single self-serve surface for students to see real options and request cleanly

## Why Ballbox

- why Ballbox is better than generic tools:
  - Ballbox can put a requestable student surface in front of real availability context
  - Ballbox has a path to real club/court context that generic tools do not
- where ATC enters the wedge:
  - read real availability and booking context
  - strengthen class discovery with actual club/court state
  - enable later workflow closure like coordination, reprogramming, or scheduling actions
- minimum ATC depth: default assume `read+write` unless this PRD is explicitly a temporary technical stepping stone

## MVP loop

- trigger: a student wants to find and request a viable class slot
- key steps:
  - browse offers under `/classes`
  - inspect one offer with ATC-backed context
  - submit `solicitar`
  - persist request in Ballbox
  - give the student clear confirmation that the request was captured
- end state: a viable request reaches Ballbox without manual back-and-forth first
- success event: student completes a real request flow through Ballbox and the coach avoids the previous manual first-step coordination

## Included

- one narrow student request flow
- Ballbox-local coaches and offers
- ATC-backed public-read context if available

## Explicitly excluded

- broad CRM
- full club ERP
- multi-workflow coach suite
- anything not needed for the first loop

## Key assumptions

- student self-serve request is a meaningful way to reduce coach coordination load
- users value clearer requestability over fragmented messaging/tools
- ATC public-read access is enough to make offers feel grounded in real supply

## Success metrics

- leading metric: number of real class requests submitted through Ballbox
- behavioral metric: repeated student usage or repeated request creation
- qualitative signal: coach says Ballbox reduced manual first-step coordination

## Risks

- user loves it, buyer differs
- ATC access depth is insufficient for workflow closure
- pain is real but too fragmented

## Decision gate

- build now if student request feels like a clear, explainable self-serve wedge
- keep validating if request flow is useful but too weak to change coach behavior
- change wedge if `/classes` does not reduce enough coordination or fails to feel differentiated
