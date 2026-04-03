# CAE-CLI Phase 1 Stability Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the diagnosis foundation stable enough to share publicly by improving rule coverage, building a repeatable real-sample corpus, normalizing output, and limiting auto-fix to safe whitelist cases.

**Architecture:** Keep the product centered on deterministic diagnosis. The rule layer stays primary, the sample corpus becomes the regression gate, output formatting becomes a separate quality target, and auto-fix is restricted to low-risk structural edits only. Do not expand scope into training, RAG, or enterprise workflow in this phase.

**Tech Stack:** Python, Typer CLI, pytest, JSON fixtures, existing `cae.ai.diagnose` and `cae.ai.fix_rules` modules

---

## Scope and Exit Criteria

This phase is complete only when all of the following are true:

- The tool reliably detects the top 20-30 high-frequency error families.
- A regression corpus of 30-50 diagnosis samples exists and can be rerun locally.
- Diagnosis output is deduplicated, consistently ordered, and easy to read.
- Auto-fix supports only a small whitelist of deterministic safe edits.
- You have 5 demo cases that can be used in a forum post.

Non-goals for this phase:

- Model fine-tuning
- Knowledge graph or RAG
- Enterprise API design
- Full automation without user confirmation
- Broad support for risky physics-changing fixes

## Two-Week Schedule

**Week 1**

- Day 1: Freeze scope, define error-family list, create fixture directory structure.
- Day 2: Add fixture schema and first 10 real or semi-real cases.
- Day 3: Add deduplication and priority-order regression tests.
- Day 4: Normalize diagnosis output structure in code.
- Day 5: Expand top missing rules and update corpus to 20+ cases.
- Day 6: Validate false positives and tighten noisy rules.
- Day 7: Reserve as buffer and cleanup day.

**Week 2**

- Day 8: Define safe auto-fix whitelist and add failing tests.
- Day 9: Implement first safe fixes and backup or diff behavior.
- Day 10: Add post-fix verification flow for whitelist cases.
- Day 11: Add 5 end-to-end demo cases and expected outputs.
- Day 12: Run full regression, document known gaps, polish CLI text.
- Day 13: Prepare public-facing screenshots, sample output, and support matrix.
- Day 14: Write and review the forum post draft.

### Task 1: Build the Diagnosis Sample Corpus

**Files:**
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\README.md`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\schema.json`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\syntax\broken_keyword\input.inp`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\syntax\broken_keyword\stderr.txt`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\syntax\broken_keyword\expected.json`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\material\missing_elastic\input.inp`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\material\missing_elastic\stderr.txt`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\material\missing_elastic\expected.json`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\boundary\rigid_body_mode\input.inp`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\boundary\rigid_body_mode\stderr.txt`
- Create: `D:\CAE-CLI\cae-cli\tests\fixtures\diagnosis_cases\boundary\rigid_body_mode\expected.json`
- Create: `D:\CAE-CLI\cae-cli\tests\test_diagnosis_fixture_corpus.py`

**Step 1: Write the failing test**

```python
from pathlib import Path
import json


def test_diagnosis_fixture_cases_have_expected_files():
    root = Path("tests/fixtures/diagnosis_cases")
    case_dirs = [p for p in root.rglob("*") if p.is_dir() and (p / "expected.json").exists()]
    assert case_dirs, "no diagnosis fixture cases found"
    for case_dir in case_dirs:
        assert (case_dir / "input.inp").exists()
        assert (case_dir / "stderr.txt").exists()
        data = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
        assert "expected_issue_keys" in data
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagnosis_fixture_corpus.py -v`  
Expected: FAIL because the fixture corpus does not exist yet.

**Step 3: Write minimal implementation**

- Create the fixture directory tree.
- Add a short README that defines:
  - one folder per case
  - required files
  - naming convention
  - source type: official sample, synthetic, forum sample, self-made
- Add 10 seed cases first:
  - syntax
  - material
  - boundary
  - load
  - contact
  - convergence
  - units

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_diagnosis_fixture_corpus.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add tests/fixtures/diagnosis_cases tests/test_diagnosis_fixture_corpus.py
git commit -m "test: add diagnosis sample corpus scaffold"
```

### Task 2: Turn the Corpus Into a Regression Harness

**Files:**
- Modify: `D:\CAE-CLI\cae-cli\tests\诊断规则批量测试.py`
- Create: `D:\CAE-CLI\cae-cli\tests\test_diagnosis_regression_cases.py`
- Modify: `D:\CAE-CLI\cae-cli\cae\ai\diagnose.py`

**Step 1: Write the failing test**

```python
def test_regression_case_matches_expected_issue_keys(sample_case):
    result = run_case(sample_case)
    assert result.success
    found = {issue.category for issue in result.issues}
    for key in sample_case.expected_issue_keys:
        assert key in found
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagnosis_regression_cases.py -v`  
Expected: FAIL because there is no fixture loader or regression runner.

**Step 3: Write minimal implementation**

- Add a helper that loads `input.inp`, `stderr.txt`, and `expected.json`.
- Reuse existing diagnosis entry points from `cae.ai.diagnose`.
- Make the regression tests check:
  - expected issue categories appear
  - severity matches when specified
  - suggested auto-fix eligibility matches when specified

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_diagnosis_regression_cases.py -v`  
Expected: PASS with the initial 10 cases.

**Step 5: Commit**

```bash
git add tests/诊断规则批量测试.py tests/test_diagnosis_regression_cases.py cae/ai/diagnose.py
git commit -m "test: add diagnosis regression harness"
```

### Task 3: Normalize, Deduplicate, and Order Diagnosis Output

**Files:**
- Modify: `D:\CAE-CLI\cae-cli\cae\ai\diagnose.py`
- Modify: `D:\CAE-CLI\cae-cli\cae\main.py`
- Create: `D:\CAE-CLI\cae-cli\tests\test_diagnosis_output_format.py`

**Step 1: Write the failing test**

```python
def test_diagnosis_output_is_deduplicated_and_sorted():
    issues = make_duplicate_issues()
    normalized = normalize_issues(issues)
    assert len(normalized) == 2
    assert normalized[0].severity == "error"
    assert normalized[0].priority <= normalized[1].priority
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagnosis_output_format.py -v`  
Expected: FAIL because no normalization function exists.

**Step 3: Write minimal implementation**

- Add a normalization layer inside `cae.ai.diagnose` or a helper it calls.
- Define one stable output contract:
  - title
  - severity
  - category
  - cause
  - action
  - priority
  - auto_fixable
- Deduplicate by normalized message key, not raw string equality.
- Sort by:
  - severity
  - priority
  - category
  - stable message key
- Update CLI rendering in `cae.main` to print:
  - diagnosis summary
  - top priority problem
  - first action to take

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_diagnosis_output_format.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add cae/ai/diagnose.py cae/main.py tests/test_diagnosis_output_format.py
git commit -m "feat: normalize diagnosis output"
```

### Task 4: Expand Top Error-Family Coverage, Not Raw Rule Count

**Files:**
- Modify: `D:\CAE-CLI\cae-cli\calculix_patterns.txt`
- Modify: `D:\CAE-CLI\cae-cli\cae\ai\diagnose.py`
- Modify: `D:\CAE-CLI\cae-cli\tests\诊断规则批量测试.py`
- Create: `D:\CAE-CLI\cae-cli\docs\plans\phase1-error-families.md`

**Step 1: Write the failing test**

```python
def test_top_error_family_cases_are_covered():
    report = evaluate_top_error_families()
    assert report["covered_families"] >= 20
    assert report["missed_cases"] == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/"诊断规则批量测试.py" -v`  
Expected: FAIL because the top-family target is not formalized.

**Step 3: Write minimal implementation**

- Create `phase1-error-families.md` listing the 20-30 target families.
- Add or refine rules only for those families first.
- Prefer family coverage over many near-duplicate patterns.
- For each new family:
  - add one fixture case
  - add one expected diagnosis
  - add one regression assertion

Recommended starting families:

- syntax error
- missing elastic
- missing density where required
- load vector zero
- boundary missing
- rigid body mode
- zero pivot
- singular matrix
- convergence failure
- increment stagnation
- contact definition issue
- step missing
- unit inconsistency
- unrealistic displacement
- unrealistic stress
- mesh quality warning
- material yield exceeded
- output file missing
- unsupported keyword
- parameter syntax error

**Step 4: Run test to verify it passes**

Run: `pytest tests/"诊断规则批量测试.py" -v`  
Expected: PASS for the selected family list.

**Step 5: Commit**

```bash
git add calculix_patterns.txt cae/ai/diagnose.py tests/诊断规则批量测试.py docs/plans/phase1-error-families.md
git commit -m "feat: expand top diagnosis error-family coverage"
```

### Task 5: Restrict Auto-Fix to a Safe Whitelist

**Files:**
- Modify: `D:\CAE-CLI\cae-cli\cae\ai\fix_rules.py`
- Modify: `D:\CAE-CLI\cae-cli\cae\main.py`
- Create: `D:\CAE-CLI\cae-cli\tests\test_safe_autofix_whitelist.py`
- Create: `D:\CAE-CLI\cae-cli\docs\plans\phase1-autofix-whitelist.md`

**Step 1: Write the failing test**

```python
def test_autofix_rejects_non_whitelist_physics_changing_issue():
    issue = make_issue(category="boundary", message="missing boundary value")
    result = fix_inp(inp_file, [issue])
    assert result.success is False
    assert "whitelist" in (result.error or "").lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_safe_autofix_whitelist.py -v`  
Expected: FAIL because the whitelist gate is not explicit.

**Step 3: Write minimal implementation**

- Add an explicit whitelist document and code gate.
- Safe whitelist for Phase 1 only:
  - add missing `*ELASTIC` with placeholder default
  - add missing `*STEP` skeleton
  - reduce clearly too-large initial static increment
  - repair deterministic structural card placement issues
- Anything that changes physical meaning stays blocked:
  - load magnitude
  - boundary values
  - contact parameters
  - real material values
  - mesh density
- Update CLI text to say:
  - safe auto-fix only
  - backup path
  - fixed file path
  - summary of changes

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_safe_autofix_whitelist.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add cae/ai/fix_rules.py cae/main.py tests/test_safe_autofix_whitelist.py docs/plans/phase1-autofix-whitelist.md
git commit -m "feat: enforce safe autofix whitelist"
```

### Task 6: Add Post-Fix Verification for Whitelist Cases

**Files:**
- Modify: `D:\CAE-CLI\cae-cli\cae\ai\fix_rules.py`
- Modify: `D:\CAE-CLI\cae-cli\cae\main.py`
- Create: `D:\CAE-CLI\cae-cli\tests\test_autofix_verification.py`

**Step 1: Write the failing test**

```python
def test_safe_autofix_result_contains_verification_status():
    result = apply_and_verify_fix(case_path)
    assert result.success
    assert result.verification_status in {"passed", "skipped", "failed"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_autofix_verification.py -v`  
Expected: FAIL because verification status is not tracked.

**Step 3: Write minimal implementation**

- Extend the fix result model with:
  - `verification_status`
  - `verification_notes`
- For Phase 1, verification can be lightweight:
  - confirm the missing card now exists
  - rerun deterministic diagnosis on the fixed file when cheap
  - if full solve is too heavy, mark as `skipped`
- Never claim a physics fix is validated if only structure was checked.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_autofix_verification.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add cae/ai/fix_rules.py cae/main.py tests/test_autofix_verification.py
git commit -m "feat: add whitelist autofix verification status"
```

### Task 7: Prepare Five Public Demo Cases

**Files:**
- Create: `D:\CAE-CLI\cae-cli\examples\diagnosis_demo_cases\README.md`
- Create: `D:\CAE-CLI\cae-cli\examples\diagnosis_demo_cases\case01_missing_elastic.md`
- Create: `D:\CAE-CLI\cae-cli\examples\diagnosis_demo_cases\case02_rigid_body_mode.md`
- Create: `D:\CAE-CLI\cae-cli\examples\diagnosis_demo_cases\case03_zero_load.md`
- Create: `D:\CAE-CLI\cae-cli\examples\diagnosis_demo_cases\case04_convergence.md`
- Create: `D:\CAE-CLI\cae-cli\examples\diagnosis_demo_cases\case05_unit_mismatch.md`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_demo_case_docs_exist():
    root = Path("examples/diagnosis_demo_cases")
    docs = list(root.glob("case*.md"))
    assert len(docs) >= 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_demo_case_docs.py -v`  
Expected: FAIL because the demo docs do not exist.

**Step 3: Write minimal implementation**

For each demo case document, include:

- problem description
- broken input summary
- diagnosis summary
- recommended fix
- whether auto-fix is allowed
- before or after excerpt

Use only cases that are easy to explain in one screenshot.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_demo_case_docs.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add examples/diagnosis_demo_cases
git commit -m "docs: add diagnosis demo cases for public feedback"
```

### Task 8: Draft the Forum Post Around User Pain, Not AI Hype

**Files:**
- Create: `D:\CAE-CLI\cae-cli\docs\plans\2026-04-03-forum-post-draft.md`

**Step 1: Write the draft**

Use this structure:

1. What problem you are solving  
   Example: "I am building a small CalculiX diagnosis tool focused on the most common error debugging workflow."

2. What already works  
   - detects high-frequency errors
   - gives repair suggestions
   - supports a few safe auto-fixes
   - has regression samples

3. What feedback you want  
   - your most common three error types
   - whether you care more about explanation or auto-fix
   - whether you would share anonymized failing cases

4. What you are not claiming  
   - not a full CAE platform
   - not replacing ANSYS or Abaqus
   - not fully automatic physics correction

**Step 2: Review it against the product position**

Checklist:

- no inflated claims
- no comparison with large vendors on breadth
- clear narrow scope
- specific ask for user pain points

**Step 3: Commit**

```bash
git add docs/plans/2026-04-03-forum-post-draft.md
git commit -m "docs: add public feedback forum post draft"
```

## Definition of Done Checklist

Before posting publicly, verify all items below:

- `pytest tests/test_diagnosis_fixture_corpus.py -v`
- `pytest tests/test_diagnosis_regression_cases.py -v`
- `pytest tests/test_diagnosis_output_format.py -v`
- `pytest tests/test_safe_autofix_whitelist.py -v`
- `pytest tests/test_autofix_verification.py -v`
- `pytest tests/"诊断规则批量测试.py" -v`

Manual checks:

- run 5 demo cases end to end
- verify no duplicate issue display
- verify summary always shows top priority action
- verify auto-fix never edits high-risk physics parameters
- verify every public screenshot uses understandable wording

## Success Metrics for This Phase

- 30-50 regression cases available locally
- 20-30 high-frequency error families covered
- duplicate issue rate close to zero in demo cases
- whitelist auto-fix success rate above 60 percent on supported cases
- 5 publishable demo cases ready for screenshots and sharing

## What to Do Immediately After This Phase

Do not start fine-tuning or RAG next.

Do these first:

- post the demo publicly
- collect at least 10 pieces of user feedback
- collect at least 5 real failing cases from other users
- rank the next rule work by frequency, not by novelty

