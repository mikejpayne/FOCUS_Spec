#!/usr/bin/env python3
"""Extract FOCUS Requirements Model from specification markdown files.

Walks the FOCUS specification markdown, parses Requirements sections using
a proper markdown AST (markdown-it-py), extracts BCP14 normative text, and
produces structured JSON rule files matching the Requirements Model format.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent dir for import of build_helpers
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_helpers import init_logger

from extraction.lib.discovery import discover_files
from extraction.lib.output_writers import diff_against_gold, write_combined, write_rules
from extraction.lib.parsing import extract_sections, parse_markdown
from extraction.lib.rules import generate_rules


def load_contract(contract_path):
    """Load and return the requirements model contract JSON."""
    with open(contract_path, "r") as f:
        return json.load(f)


def get_args():
    parser = argparse.ArgumentParser(
        description="Extract FOCUS Requirements Model from specification markdown."
    )
    parser.add_argument("--contract", type=str,
        default=str(Path(__file__).parent / "requirements_model_contract.json"),
        help="Path to requirements_model_contract.json")
    parser.add_argument("--spec-root", type=str,
        default=str(Path(__file__).resolve().parent.parent.parent.parent),
        help="Path to the spec repository root")
    parser.add_argument("--output", type=str,
        default=str(Path(__file__).parent / "output"),
        help="Output directory for extracted JSON")
    parser.add_argument("--version", type=str, default="",
        help="Model version string (e.g. 1.3)")
    parser.add_argument("--diff", type=str, default=None,
        help="Path to gold standard model_rules directory for comparison")
    parser.add_argument("--log-level", type=str, default="INFO",
        choices={"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
        help="Logging level")
    parser.add_argument("--single-file", type=str, default=None,
        help="Process only a single markdown file (for testing)")
    return parser.parse_args()


def main():
    args = get_args()
    logger = init_logger(args.log_level)

    contract = load_contract(args.contract)
    logger.info(f"Loaded contract from {args.contract}")

    spec_root = Path(args.spec_root).resolve()
    logger.info(f"Spec root: {spec_root}")

    # Discover files
    all_targets = discover_files(contract, spec_root, logger)

    if args.single_file:
        filepath = Path(args.single_file).resolve()
        targets = [t for t in all_targets if t.filepath.resolve() == filepath]
        if not targets:
            logger.error(f"Could not find {filepath} in discovered targets")
            sys.exit(1)
    else:
        targets = all_targets

    if not targets:
        logger.error("No files discovered")
        sys.exit(1)

    # Process each file
    all_rules = {}
    all_skipped = {}
    processed_files = 0
    skipped_files = 0

    for target in targets:
        logger.info(f"Processing: {target.filepath.name} ({target.entity_type})")
        tokens, _ = parse_markdown(target.filepath)
        sections = extract_sections(tokens, logger, target.filepath.name)

        rules, skipped = generate_rules(target, sections, contract, args.version, logger)
        if skipped:
            label = f"{target.filepath.name} ({target.entity_type}: {target.dataset_id or target.entity_type})"
            all_skipped[label] = skipped
        if rules:
            write_rules(rules, args.output, target, logger)
            all_rules.update(rules)
            processed_files += 1
        else:
            skipped_files += 1

    # Write combined output
    if all_rules:
        combined_path = Path(args.output) / "all_rules.json"
        write_combined(all_rules, combined_path, logger)

    # Print summary
    print(f"\nExtracted {len(all_rules)} rules from {processed_files} files")
    if skipped_files:
        print(f"Skipped {skipped_files} files (no rules extracted)")

    # Report skipped bullets
    if all_skipped:
        total_skipped = sum(len(v) for v in all_skipped.values())
        print(f"\n{total_skipped} bullets skipped (no known verb):")
        for filename, bullets in all_skipped.items():
            for text in bullets:
                print(f"  {filename}: {text[:120]}")

        log_path = Path(args.output) / "skipped_bullets.log"
        with open(log_path, "w") as f:
            for filename, bullets in all_skipped.items():
                for text in bullets:
                    f.write(f"{filename}: {text}\n")
        print(f"Full log: {log_path}")

    # Diff against gold standard
    if args.diff:
        diff_against_gold(all_rules, args.diff, logger)


if __name__ == "__main__":
    main()
