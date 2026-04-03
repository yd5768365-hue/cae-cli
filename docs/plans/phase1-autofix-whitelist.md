# Phase 1 Auto-Fix Whitelist

This document defines what `cae diagnose` is allowed to auto-fix in Phase 1.

## Policy

Auto-fix is restricted to deterministic, low-risk structural edits.

Allowed:

- Missing `*ELASTIC` under an existing `*MATERIAL` block
- Missing `*STEP` block when the input deck has no analysis step
- Clearly too-large initial increment in `*STATIC`

Blocked:

- Load magnitude changes
- Boundary value changes
- Contact parameter changes
- Real material value changes
- Mesh density changes
- Any repair that changes the intended physics without explicit user judgment

## Why

The goal of Phase 1 is trust, not breadth.

If the tool silently edits loads, constraints, or contact settings, it can produce a numerically cleaner model while hiding a physically wrong one. That is unacceptable for a single-developer early-stage tool.

## CLI Behavior

- Only whitelist issues are offered for auto-fix.
- The original input file is always backed up.
- The fixed result is written to a separate file.
- If only blocked issues are present, the tool must refuse automatic repair.
