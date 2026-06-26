# Requirements Model Extraction

Parses FOCUS specification markdown files and extracts normative requirements into structured JSON matching the Requirements Model format.

## How it works

1. **Discovery** — walks the spec tree using `requirements_model_contract.json` to find columns, datasets, attributes, and the data model file
2. **Parsing** — builds a markdown AST (via `markdown-it-py`) and pulls out Requirements sections, tables, and BCP14 bullets
3. **Rule generation** — converts parsed bullets into RM rule structures with IDs, keywords, conditions, and feature levels
4. **Output** — writes per-entity JSON files plus a combined `all_rules.json` to the output directory

## Dependencies

Requires `markdown-it-py`:

```bash
pip install markdown-it-py
```

## Usage

From `specification/requirements_model/`:

```bash
python -m extraction.extract_rm
```

### Options

| Flag | Description |
|------|-------------|
| `--spec-root <path>` | Spec repo root (default: auto-detected) |
| `--contract <path>` | Contract JSON (default: `requirements_model_contract.json`) |
| `--output <dir>` | Output directory (default: `extraction/output/`) |
| `--version <ver>` | Model version string, e.g. `1.3` |
| `--single-file <path>` | Process one markdown file only |
| `--diff <path>` | Compare output against a gold-standard `model_rules/` directory |
| `--log-level <level>` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

### Examples

Extract everything:

```bash
python -m extraction.extract_rm --version 1.3
```

Extract a single column with debug logging:

```bash
python -m extraction.extract_rm --single-file ../../../specification/datasets/cost_and_usage/columns/billedcost.md --log-level DEBUG
```

Diff against existing model rules:

```bash
python -m extraction.extract_rm --diff ../model_rules
```

## Output

Output is written to `extraction/output/` (gitignored). Includes:

* Per-entity JSON files mirroring the `model_rules/` structure
* `all_rules.json` — combined output
* `skipped_bullets.log` — any bullets that couldn't be classified

## Contract

The `requirements_model_contract.json` file drives discovery. It defines:

* Dataset type prefixes (e.g. `CostAndUsage` → `CAU`)
* Where to find markdown files in the spec tree
* Which headings to look for in each entity type
* The mapping from BCP14 keywords to feature levels
