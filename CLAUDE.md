# E-Discovery Review Agent

## What this is
An AI-assisted e-discovery cockpit built for the UK AI Agent Hackathon 
EP5, Conduct.ai track.

## Ground truth
`docs/ediscovery-technical-spec.md` is the source of truth for all 
architecture, stack choices, tool specs, data models, and constraints. 
If anything in this file or in a chat conflicts with the spec, the 
spec wins. Read it before starting any task.

Also read before starting:
- `docs/decisions.md` — why choices were made
- `docs/repo-structure.md` — current layout of the repo

## Dev defaults
These are config variables, not hardcoded values — check the spec for 
rationale:
- LLM model: Haiku for dev, Sonnet for eval/demo
- Batch size: 5 for dev, 25 for demo
- Corpus size: subset during dev, full corpus for final eval

## Hard rules
- No agent frameworks (LangChain, LangGraph, etc.)
- No Next.js
- No secrets committed to the repo (.env only)
- Corpus data and DB files live outside the repo