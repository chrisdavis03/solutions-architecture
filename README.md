# solutions-architecture

My solutions-architecture lab: a place to write down designs, decisions, patterns, and study notes as I work through problems. Everything is plain Markdown, so there is no build step, no site generator, and nothing to deploy — open a file and read it. It is private-first with occasional publication, so some material is polished and some is a rough working note.

## What lives where

| Path | What belongs there |
|------|--------------------|
| `posts/` | Dated write-ups meant to be read on their own: a problem, a solution, tradeoffs, a TL;DR. Drafts and published pieces both live here. |
| `patterns/` | Reusable solution write-ups: problem, context, solution, tradeoffs, when *not* to use it. Reference material, not a diary. |
| `notes/` | Study notes, cert prep, learning scratchpads. Raw is fine. |
| `templates/` | Skeletons to copy: design doc, ADR. The post skeleton lives at `posts/_template.md`. Not content in their own right. |
| `diagrams/` | Diagram sources (`.drawio`) and rendered exports (PNG/SVG). |
| `examples/` | Runnable reference systems backing a post or pattern. Each is self-contained, with its own README, tests, and infra. |

## Conventions

Every post in `posts/` starts with frontmatter:

```yaml
---
title:    # the post title
date:     # YYYY-MM-DD
status:   # draft | published | idea
tags: []  # freeform list, e.g. [aws, networking]
---
```

- `draft` — in progress, not shown to anyone.
- `published` — finished and shareable.
- `idea` — a placeholder stub worth writing later.

ADRs use the filename `ADR-NNNN-short-title.md` (zero-padded, sequential, kebab-case), e.g. `ADR-0001-use-postgres.md`. Don't renumber or delete an ADR; to change a decision, write a new ADR and mark the old one superseded.

## Quick start

**Start a new post**

```bash
cp posts/_template.md posts/2026-11-25-my-topic.md
```

Fill in the frontmatter, set `status: draft`, write the body, then flip to `published` when it is ready.

**Start an ADR**

```bash
cp templates/adr.md ADR-0001-my-decision.md
```

Pick the next free number. Keep the title short and kebab-case. ADRs live in the repo root for now (`ADR-0001-my-decision.md`); if they grow numerous, they can be moved into their own directory later.

**Add a design doc**

```bash
cp templates/design-doc.md notes/design-my-system.md
```

Design docs are working documents, so keep them in `notes/` under a clear name; `templates/design-doc.md` has the full outline (goals, alternatives, risks, rollout).

**Add a diagram**

1. Drop the source (`foo.drawio`) or an export (`foo.png`, `foo.svg`) into `diagrams/`.
2. Commit the source and the export. Generated render artifacts go in `diagrams/.render/`, which is gitignored.
3. Link it from the post with a relative path and a one-line caption:

```markdown
![Order flow](../diagrams/order-flow.png)
```

See `diagrams/README.md` for the source-vs-export convention.
