# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**cae-cli** is a lightweight CAE (Computer-Aided Engineering) command-line tool powered by CalculiX for finite element analysis and an AI-assisted diagnosis system. Target users are mechanical engineering students and small labs who can't afford commercial software.

## Development Commands

```bash
# Install in development mode with all extras
pip install -e ".[dev,ai,mesh,report]"

# Run tests
pytest tests/ -v

# Run a single test file
pytest tests/诊断规则批量测试.py -v

# Lint with ruff
ruff check cae/

# Format with ruff (if needed)
ruff format cae/
```

## Architecture

### CLI Entry Point
- `cae/main.py` — Typer-based CLI with subcommands: `solve`, `diagnose`, `inp`, `mesh`, `view`, `test`, `report`, `setting`, `install`

### Module Structure
```
cae/
├── inp/           # INP file parsing, keywords (kw_list.json), templates
├── solvers/       # Solver abstraction (BaseSolver) + CalculiX implementation
├── mesh/          # Gmsh integration, meshio conversion
├── material/      # Elastic, Plastic, HyperElastic material models
├── contact/       # ContactPair, SurfaceInteraction, Friction, Tie, Gap
├── coupling/      # Coupling constraints, MPC
├── viewer/        # FRD/DAT parsing, VTK export, HTML/PDF reports
├── ai/            # LLM client, 3-level diagnosis (rules/cases/AI)
├── installer/     # Solver and AI model installation
└── config/        # Settings using platformdirs (cross-platform config paths)
```

### Protocol-Based Design
All keyword classes implement `IKeyword` protocol (from `cae/protocols.py`):
- `keyword_name: str` — INP keyword (e.g., "*ELASTIC")
- `to_inp_lines() -> list[str]` — Convert to INP format

Step classes implement `IStep` protocol with `step_keywords` and `add_step_keywords()`.

### Three-Level AI Diagnosis System
Located in `cae/ai/`:
1. **Level 1 (Rule Detection)** — 527 CalculiX source hardcoded error patterns, 0 LLM calls
2. **Level 2 (Reference Cases)** — 638 official test cases for physical data comparison
3. **Level 3 (AI Analysis)** — Optional LLM inference with CalculiX syntax constraints

Key files:
- `diagnose.py` — Main diagnosis orchestrator
- `fix_rules.py` — Auto-fix rules for detected problems
- `reference_cases.py` — Case database for Level 2
- `prompts.py` — Prompt templates with built-in Abaqus syntax prohibitions

### Solver Architecture
- `solvers/base.py` — `BaseSolver` abstract class with `SolveResult` dataclass
- `solvers/calculix.py` — CalculiX implementation
- `solvers/registry.py` — Solver registration and discovery

### Configuration
- Uses `platformdirs` for cross-platform paths (config in `%APPDATA%/cae-cli` on Windows)
- `Settings` class in `cae/config/__init__.py` manages JSON-based configuration
- Workspace setup creates `output/` and `solvers/` subdirectories

### INP Keywords
- `kw_list.json` — 135 CalculiX keywords with parameters
- `kw_tree.json` — Keyword classification tree
- Keywords follow `IKeyword` protocol with `to_inp_lines()` method

### Result File Formats
- `.frd` — CalculiX displacement/stress results (parsed by `viewer/frd_parser.py`)
- `.dat` — CalculiX output data (parsed by `viewer/dat_parser.py`)
- `.vtu` — VTK format for visualization

## Key Conventions

- All keyword classes use dataclasses with `to_inp_lines()` method
- Protocol interfaces (`IKeyword`, `IStep`) enable runtime type checking
- Solver implementations inherit from `BaseSolver` and register in `registry.py`
- AI features are optional (`[ai]` extra) to minimize dependencies
- Windows UTF-8 encoding enforced via `PYTHONIOENCODING` environment variable

## Testing

Tests are in `tests/` directory with Chinese naming. Run full suite with `pytest tests/ -v`. Test data includes `ccx_2.23.test/` (CalculiX official test suite with 638 .inp files).
