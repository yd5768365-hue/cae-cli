<div align="center">
  <img src="logo.svg" alt="cae-cli" width="380">
  <h1>cae-cli</h1>
  <p>A lightweight CAE command-line tool: run a simulation with one command and inspect results with one link.</p>
  <p>Built around <a href="https://www.calculix.org/">CalculiX</a>, with support for meshing, solving, visualization, diagnosis, and reporting.</p>
</div>

<p align="center">
  <a href="https://github.com/yd5768365-hue/cae-cli">GitHub</a> ·
  <a href="https://pypi.org/project/cae-cxx/">PyPI</a> ·
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

# Use DeepSeek for diagnosis
cae diagnose results/ --ai --provider deepseek
```

---

## Project Structure

```text
cae-cli/
├─ cae/                  # Main code
│  ├─ main.py            # CLI entry point (Typer)
│  ├─ inp/               # INP parsing, inspection, editing, and templates
│  ├─ mesh/              # Mesh-related features
│  ├─ solvers/           # Solver abstraction and registry
│  ├─ viewer/            # FRD parsing, conversion, visualization, and reports
│  ├─ ai/                # Diagnosis and AI features
│  ├─ installer/         # Solver/model installation
│  └─ config/            # Configuration management
├─ tests/                # Tests
└─ README.md
```

---

## Development

```bash
git clone https://github.com/yd5768365-hue/cae-cli
cd cae-cli
pip install -e ".[dev,ai,mesh,report]"
pytest tests/ -v
ruff check cae/
```

---

## License

MIT. See [LICENSE](LICENSE).
