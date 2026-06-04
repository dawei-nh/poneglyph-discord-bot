# Agent Guidelines

This repository is planned for subagent-driven implementation. These guidelines
apply to every agent working in this repo.

## Source Of Truth

- Follow `docs/superpowers/plans/2026-06-04-slash-first-poneglyph-discord-bot.md`.
- Use the design spec at
  `docs/superpowers/specs/2026-06-04-slash-first-poneglyph-discord-bot-design.md`
  for product intent and edge-case decisions.
- Work one plan task at a time. Do not skip ahead, combine unrelated tasks, or
  broaden scope without explicit user approval.

## Implementation Discipline

- Use `nix develop` before running project commands. The shell provides Python
  3.12, `uv`, Node.js for Pyright, and CA certificates for HTTPS tooling.
- Use TDD for implementation tasks: write the failing test, run it, implement
  the smallest change, then rerun the task verification commands.
- Commit after each completed task using the commit message from the plan.
- Before reporting a task complete, run the verification commands listed for
  that task and inspect the output.
- Keep changes scoped to the files named in the current task unless a required
  fix is impossible without touching another file. If another file is needed,
  explain why in the handoff.

## Product Rules

- Preserve Poneglyph search syntax. Strip only Discord command wrappers and
  bot-owned options; do not invent or rewrite a bot-specific query language.
- `/card` posts direct card-number and exactly-one-result matches publicly.
  Ambiguous matches use an ephemeral picker.
- `/search` is private-first and returns ephemeral browse results.
- `/random` posts publicly immediately.
- `/faq` displays official FAQ entries only from `official_faq`. Do not fall
  back to card text.
- `[[card-name]]` message lookup is a Phase 2 feature and must reuse the same
  resolver as `/card`.

## API And Test Guardrails

- Treat Poneglyph's vendored OpenAPI contract as the upstream API source of
  truth, but keep live smoke tests narrow.
- Do not assert volatile prices, market URLs, total result counts, or
  `card_number:OP01-001` search behavior in live tests.
- Direct `GET /v1/cards/OP01-001` and bare search `q=OP01-001` are the stable
  live card-number checks.
- Missing images, missing prices, and missing optional card fields must degrade
  gracefully.

## Git Hygiene

- Never commit unrelated local files or generated artifacts.
- Never merge directly to `main`; use feature branches and pull requests.
- Do not rewrite or revert user changes unless explicitly requested.
- If the working tree contains unrelated changes, leave them alone and mention
  them in the handoff.
