# Diagnosis Fixture Corpus

This directory stores real or semi-real diagnosis cases used for regression testing.

## Layout

- One folder per case.
- Group folders by error family, for example `syntax/`, `material/`, `boundary/`.
- Each case folder must contain:
  - `input.inp`
  - `stderr.txt`
  - `expected.json`

## Naming

- Use short lowercase folder names.
- Prefer one dominant problem per case.
- If a case has multiple issues, list the primary expected issue first in `expected.json`.

## Source Types

Allowed `source_type` values in `expected.json`:

- `official_sample`
- `synthetic`
- `self_made`
- `forum_sample`

## Rules

- Keep files small and readable.
- Do not store sensitive data.
- Match expected issue keys to diagnosis categories from `cae.ai.diagnose`.
- Prefer high-frequency failure patterns over obscure edge cases.
