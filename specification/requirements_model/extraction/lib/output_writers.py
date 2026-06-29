"""Output writers — JSON files, diff reports, and GraphViz DAG generation."""

import json
from pathlib import Path

from .discovery import id_to_folder


def write_rules(rules, output_dir, target, logger):
    """Write rules to a JSON file in the appropriate output directory."""
    output_dir = Path(output_dir)

    if target.entity_type == "DataModel":
        out_path = output_dir / "datamodel.json"
    elif target.entity_type == "Column":
        folder = id_to_folder(target.dataset_id)
        col_name = target.filepath.stem
        out_path = output_dir / "datasets" / folder / "columns" / f"{col_name}.json"
    elif target.entity_type == "Dataset":
        folder = id_to_folder(target.dataset_id)
        out_path = output_dir / "datasets" / folder / f"{target.dataset_id.lower()}.json"
    elif target.entity_type == "Attribute":
        attr_name = target.filepath.stem
        out_path = output_dir / "attributes" / f"{attr_name}.json"
    else:
        out_path = output_dir / f"{target.entity_type.lower()}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(dict(sorted(rules.items())), f, indent=2)
    logger.info(f"Wrote {out_path}")
    return out_path


def write_combined(all_rules, output_path, logger):
    """Write all rules combined into a single JSON file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(dict(sorted(all_rules.items())), f, indent=2)
    logger.info(f"Wrote combined output: {output_path} ({len(all_rules)} rules)")


def diff_against_gold(extracted_rules, gold_dir, logger):
    """Compare extracted rules against gold standard JSON files."""
    gold_dir = Path(gold_dir)
    if not gold_dir.exists():
        logger.error(f"Gold standard directory not found: {gold_dir}")
        return

    gold_rules = {}
    for json_file in gold_dir.rglob("*.json"):
        with open(json_file, "r") as f:
            try:
                data = json.load(f)
                gold_rules.update(data)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse {json_file}")

    extracted_ids = set(extracted_rules.keys())
    gold_ids = set(gold_rules.keys())
    only_in_gold = gold_ids - extracted_ids
    only_in_extracted = extracted_ids - gold_ids
    common = extracted_ids & gold_ids

    print("\n" + "=" * 60)
    print("DIFF REPORT: Extracted vs Gold Standard")
    print("=" * 60)
    print(f"\nExtracted rules: {len(extracted_ids)}")
    print(f"Gold standard rules: {len(gold_ids)}")
    print(f"Common rules: {len(common)}")

    if only_in_gold:
        active_only_in_gold = {
            rid for rid in only_in_gold
            if gold_rules[rid].get("Status") != "Removed"
        }
        print(f"\nIn gold but NOT in extracted ({len(active_only_in_gold)} active):")
        for rid in sorted(active_only_in_gold):
            ms = gold_rules[rid].get("ValidationCriteria", {}).get("MustSatisfy", "")
            print(f"  - {rid}: {ms[:80]}")

    if only_in_extracted:
        print(f"\nIn extracted but NOT in gold ({len(only_in_extracted)}):")
        for rid in sorted(only_in_extracted):
            ms = extracted_rules[rid].get("ValidationCriteria", {}).get("MustSatisfy", "")
            print(f"  + {rid}: {ms[:80]}")

    field_diffs = 0
    for rid in sorted(common):
        ext = extracted_rules[rid]
        gold = gold_rules[rid]
        diffs = []
        for fld in ("Function", "EntityType", "EntityId", "Reference"):
            if ext.get(fld) != gold.get(fld):
                diffs.append(f"{fld}: '{ext.get(fld)}' vs '{gold.get(fld)}'")
        ext_kw = ext.get("ValidationCriteria", {}).get("Keyword")
        gold_kw = gold.get("ValidationCriteria", {}).get("Keyword")
        if ext_kw != gold_kw:
            diffs.append(f"Keyword: '{ext_kw}' vs '{gold_kw}'")
        if diffs:
            field_diffs += 1
            if field_diffs <= 20:
                print(f"\n  ~ {rid}:")
                for d in diffs:
                    print(f"      {d}")

    if field_diffs > 20:
        print(f"\n  ... and {field_diffs - 20} more rules with field differences")

    print(f"\nTotal rules with field differences: {field_diffs}")
    print("=" * 60 + "\n")
