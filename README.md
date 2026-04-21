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
- Standalone Docker workflow: check Docker/WSL Docker and run containerized CalculiX separately
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
- `cae docker`: standalone Docker and containerized solver tools
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

`cae docker` subcommands:

- `catalog`: list built-in solver image aliases
- `pull`: pull an image by alias or direct Docker image reference
- `images`: list local Docker images visible to the selected Docker backend
- `status`: check Docker availability, including Docker installed inside Windows WSL
- `path`: convert a Windows path to the mount path used by WSL Docker
- `calculix`: run CalculiX in a Docker container as a separate workflow

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

# Check Docker or WSL Docker
cae docker status

# Show built-in solver image aliases
cae docker catalog
cae docker catalog --capability cfd
cae docker recommend "steady CFD turbulence"

# Pull the default CalculiX image and save it for future containerized runs
cae docker pull calculix-parallelworks --set-default

# List local Docker images
cae docker images

# Convert a Windows path for WSL Docker volume mounting
cae docker path D:\CAE-CLI\case

# Run CalculiX in a Docker container, separate from native `cae solve`
cae docker calculix model.inp --image calculix:latest -o results/docker-model

# Build a local SU2 runtime image that actually exposes SU2_CFD
cae docker build-su2-runtime --tag local/su2-runtime:8.3.0

# Run the included official SU2 CFD smoke case
cae docker run su2-runtime examples/su2_inviscid_bump/inv_channel_smoke.cfg -o results/su2-inviscid-bump-smoke

# Run the included minimal Code_Aster smoke case
cae docker pull code-aster
cae docker run code-aster examples/code_aster_minimal_smoke/case.comm -o results/code-aster-smoke

# Run the included OpenFOAM cavity smoke case
cae docker pull openfoam-lite
cae docker run openfoam-lite examples/openfoam_cavity_smoke --cmd "bash -lc 'blockMesh && icoFoam'" -o results/openfoam-cavity-smoke

# Run the included Elmer smoke case
cae docker run elmer examples/elmer_steady_heat/case.sif -o results/elmer-heat
```

---

## Docker Workflow

Docker support is intentionally separate from the native solver command. Use
`cae solve` for local/native CalculiX execution and `cae docker ...` for
containerized workflows.

On Windows, `cae docker status` probes native Docker first, then Docker installed
inside WSL through `wsl -e docker`. When WSL Docker is selected, host paths are
converted to `/mnt/<drive>/...` for volume mounts.

Containerized CalculiX uses this command shape:

```bash
cae docker pull calculix-parallelworks --set-default
cae docker calculix model.inp -o results/model-docker
```

Other open-source solvers are exposed through the shared Docker catalog and
generic runner:

```bash
# CFD candidates: OpenFOAM and SU2
cae docker recommend "external aerodynamic CFD"
cae docker pull openfoam-lite
cae docker run openfoam-lite examples/openfoam_cavity_smoke --cmd "bash -lc 'blockMesh && icoFoam'" -o results/openfoam-cavity-smoke

# Structural and thermomechanical candidates: CalculiX and code_aster
cae docker recommend "nonlinear structural contact"
cae docker pull code-aster
cae docker run code-aster examples/code_aster_minimal_smoke/case.comm -o results/code-aster-smoke

# Multiphysics candidate: Elmer
cae docker recommend "thermal electromagnetic multiphysics"
cae docker pull elmer
cae docker run elmer case.sif -o results/elmer-case

# Local SU2 runtime candidate with an official CFD tutorial-derived smoke case
cae docker build-su2-runtime --tag local/su2-runtime:8.3.0
cae docker run su2-runtime examples/su2_inviscid_bump/inv_channel_smoke.cfg -o results/su2-inviscid-bump-smoke
```

The image can also be provided with `CAE_CALCULIX_DOCKER_IMAGE` or the
`docker_calculix_image` config key.
For other solver families, `cae docker pull <alias> --set-default` writes
`docker_<solver>_image`, for example `docker_code_aster_image`.

If Docker runs inside WSL and Docker Hub is slow, update WSL's
`/etc/docker/daemon.json` registry mirror and restart Docker before pulling.
The built-in catalog records per-image command paths because public solver
images do not always expose their solver launchers on `PATH`.
For SU2 `.cfg` inputs, the generic runner also copies referenced sidecar files
such as `MESH_FILENAME` and other existing `*_FILENAME` inputs into the mounted
work directory before launching the container.
For Code_Aster `.export` inputs, the generic runner also copies referenced local
sidecar files such as `.comm` or `.med` inputs into the mounted work directory
before launching the container.
`cae docker pull` reuses a local image by default; add `--refresh` when you
want to contact the remote registry again.

Built-in Docker solver aliases currently include:

| Alias | Solver | Typical use |
| --- | --- | --- |
| `calculix-parallelworks` | CalculiX | Structural/thermal FEM with `.inp` input |
| `code-aster` | code_aster | Nonlinear structure, contact, thermal mechanics |
| `openfoam-foundation-11` | OpenFOAM | Smaller official OpenFOAM Foundation v11 fallback image |
| `openfoam` | OpenFOAM | CFD case directories; override `--cmd` per solver app |
| `openfoam-lite` | OpenFOAM | Community fallback image validated with the cavity smoke case |
| `su2-runtime` | SU2 | Locally built runtime image exposing `SU2_CFD` |
| `su2` | SU2 | Build container only; not a direct `SU2_CFD` runtime image |
| `elmer` | Elmer | Multiphysics FEM with `.sif` input |

The repository includes validated smoke examples for:

- `examples/openfoam_cavity_smoke`
- `examples/su2_inviscid_bump/inv_channel_smoke.cfg`
- `examples/code_aster_minimal_smoke/case.comm`
- `examples/elmer_steady_heat/case.sif`

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
- `cae_docker_status`
- `cae_docker_catalog`
- `cae_docker_recommend`
- `cae_docker_images`
- `cae_docker_pull`
- `cae_docker_run`
- `cae_docker_build_su2_runtime`
- `cae_docker_calculix`
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
|   |-- docker/            # Standalone Docker/containerized solver features
|   |-- runtimes/          # Runtime adapters such as native or WSL Docker
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
