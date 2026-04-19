<div align="center">
  <img src="logo.svg" alt="cae-cli" width="380">
  <h1>cae-cli</h1>
  <p>A lightweight CAE command-line tool: run a simulation with one command and inspect results with one link.</p>
  <p>Built around <a href="https://www.calculix.org/">CalculiX</a>, with support for meshing, solving, visualization, diagnosis, and reporting.</p>
</div>

<p align="center">
  <a href="https://github.com/yd5768365-hue/cae-cli">GitHub</a> |
  <a href="https://pypi.org/project/cae-cxx/">PyPI</a> |
  <a href="https://github.com/yd5768365-hue/cae-cli/issues">Issues</a>
</p>

---

## Features

- End-to-end workflow: mesh generation -> solving -> visualization -> diagnosis -> PDF reporting
- Local-first execution: core computation and result processing run on your own machine
- AI-assisted diagnosis: rule-based checks + reference cases + optional deep AI analysis
- INP toolchain: inspect, view, modify, generate templates, and suggest fixes
- Automation-friendly: CLI-first design for scripting and batch integration

---

## Installation

```bash
pip install cae-cxx
```

Optional extras:

```bash
# AI features
pip install "cae-cxx[ai]"

# Mesh support (Gmsh / meshio)
pip install "cae-cxx[mesh]"

# PDF reporting (weasyprint)
pip install "cae-cxx[report]"

# MCP server integration
pip install "cae-cxx[mcp]"
```

Install CalculiX:

```bash
cae install
```

---

## Quick Start

```bash
# 1) Generate an INP template
cae inp template cantilever_beam -o beam.inp

# 2) Run the solver
cae solve beam.inp

# 3) View results in the browser (FRD is converted to VTU automatically)
cae view results/

# 4) Diagnose issues (optional)
cae diagnose results/

# 5) Generate a PDF report (optional)
cae report results/
```

---

## Command Overview

Main commands:

- `cae solve`: run an FEA solve
- `cae solvers`: inspect solver availability
- `cae info`: show configuration and version information
- `cae view`: inspect simulation results in the browser
- `cae convert`: manually convert `.frd -> .vtu`
- `cae install`: install CalculiX
- `cae ai-install`: install AI models
- `cae diagnose`: diagnose simulation issues
- `cae report`: generate a PDF report
- `cae inp`: parse and modify INP files
- `cae mesh`: meshing tools
- `cae model`: manage local Ollama models
- `cae config`: manage workspace configuration
- `cae-mcp`: run the MCP server for OpenCode and other MCP clients

`cae inp` subcommands:

- `info` / `check` / `show` / `modify` / `suggest` / `list` / `template`

`cae mesh` subcommands:

- `gen` / `check`

`cae model` subcommands:

- `list` / `pull` / `show` / `delete` / `set`

---

## Common Usage

```bash
# Solve with a specified output directory
cae solve model.inp -o results/

# Inspect and view an INP file
cae inp check model.inp
cae inp show model.inp -k *MATERIAL

# Modify an INP file (example)
cae inp modify model.inp -k *ELASTIC --set "210000, 0.3"

# Generate a mesh
cae mesh gen geo.step -o mesh.inp

# Check mesh quality/preview
cae mesh check mesh.inp

# Enable deep AI diagnosis
cae diagnose results/ --ai

# Export structured diagnosis JSON
cae diagnose results/ --json

# Export JSON to a file
cae diagnose results/ --json-out out/diagnose.json

# Override evidence guardrails config
cae diagnose results/ --json --guardrails cae/ai/data/evidence_guardrails.json

# Enable optional diagnosis history calibration (SQLite)
cae diagnose results/ --json --history-db out/diagnosis_history.db
```

---

## MCP Server (for OpenCode)

`cae-cli` can run as an MCP server over `stdio` so OpenCode can call it reliably.

Install MCP extra:

```bash
pip install "cae-cxx[mcp]"
```

Start server:

```bash
cae-mcp
```

Provided MCP tools:

- `cae_health`
- `cae_solvers`
- `cae_solve`
- `cae_diagnose`
- `cae_inp_check`

All tools return a stable envelope:

- success: `{"ok": true, "data": ...}`
- error: `{"ok": false, "error": {"code": "...", "message": "...", "details": {...}}}`

Example OpenCode MCP config:

```json
{
  "mcpServers": {
    "cae-cli": {
      "command": "python",
      "args": ["-m", "cae.mcp_server"]
    }
  }
}
```

---

## Diagnosis Output and Guardrails

`cae diagnose --json` exports structured issues with grounded evidence fields:

- `evidence_line`: `file:line: excerpt` evidence for the issue
- `evidence_score`: confidence score in `[0,1]`
- `evidence_support_count`: number of independent files supporting the issue
- `evidence_conflict`: contradiction note when evidence trends conflict

Guardrail thresholds are category-aware and configurable:

- Default config path: `cae/ai/data/evidence_guardrails.json`
- CLI override: `--guardrails <path>`
- Environment override: `CAE_EVIDENCE_GUARDRAILS_PATH=<path>`

You can also enable history-consistency calibration:

- CLI option: `--history-db <path>`
- Environment fallback: `CAE_DIAG_HISTORY_DB_PATH=<path>`
- JSON fields per issue:
  `history_hits`, `history_avg_score`, `history_conflict_rate`,
  `history_similarity`, `history_similar_hits`, `history_similar_conflict_rate`

The default guardrails file also supports a `default` bucket, used as fallback for
categories without an explicit entry.

When evidence is weak or contradictory for sensitive categories, severity can be
automatically downgraded (for example `error -> warning`) to reduce false positives.

---

## Project Structure

```text
cae-cli/
|-- cae/                  # Main code
|   |-- main.py            # CLI entry point (Typer)
|   |-- mcp_server.py      # MCP stdio server
|   |-- inp/               # INP parsing, inspection, editing, and templates
|   |-- mesh/              # Mesh-related features
|   |-- solvers/           # Solver abstraction and registry
|   |-- viewer/            # FRD parsing, conversion, visualization, and reports
|   |-- ai/                # Diagnosis and AI features
|   |-- installer/         # Solver/model installation
|   `-- config/            # Configuration management
|-- tests/                # Tests
`-- README.md
```

---

## Development

```bash
git clone https://github.com/yd5768365-hue/cae-cli
cd cae-cli
pip install -e ".[dev,ai,mesh,report,mcp]"
python -m pytest
python -m ruff check cae/ tests/
```

---

## License

MIT. See [LICENSE](LICENSE).
