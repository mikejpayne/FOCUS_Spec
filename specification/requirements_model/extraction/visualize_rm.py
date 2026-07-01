#!/usr/bin/env python3
"""Generate a Graphviz diagram from extracted Requirements Model JSON."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# Colours by status suffix
STATUS_COLOURS = {
    "M": "#e74c3c",   # Mandatory — red
    "O": "#3498db",   # Optional  — blue
    "C": "#f39c12",   # Conditional — amber
}

FUNCTION_SHAPES = {
    "Composite": "folder",
    "Type": "box",
    "Format": "box",
    "Nullability": "box",
    "Validation": "box",
}


def status_colour(rule_id: str) -> str:
    suffix = rule_id.rsplit("-", 1)[-1]
    return STATUS_COLOURS.get(suffix, "#95a5a6")


def load_json_files(output_dir: Path) -> dict:
    """Walk output_dir and merge all JSON files into one dict."""
    merged = {}
    for root, _, files in os.walk(output_dir):
        for f in files:
            if f.endswith(".json"):
                with open(os.path.join(root, f)) as fh:
                    merged.update(json.load(fh))
    return merged


def build_dot(rules: dict, title: str = "Requirements Model") -> str:
    lines = [
        "digraph RM {",
        '  rankdir=LR;',
        '  bgcolor="#fafafa";',
        f'  label="{title}";',
        '  labelloc=t;',
        '  fontsize=18;',
        '  fontname="Helvetica";',
        '  node [fontname="Helvetica", fontsize=10, style=filled];',
        '  edge [color="#7f8c8d"];',
        '  nodesep=0.4;',
        '  ranksep=0.8;',
        "",
    ]

    # Group nodes by dataset + entity for clearer clusters
    clusters = {}
    for rule_id, rule in rules.items():
        dataset = rule.get("DatasetName", "General")
        entity = rule.get("EntityId", "Unknown")
        key = (dataset, entity)
        clusters.setdefault(key, []).append(rule_id)

    for (dataset, entity), rule_ids in sorted(clusters.items()):
        cluster_id = f"{dataset}_{entity}".replace(" ", "_")
        lines.append(f'  subgraph "cluster_{cluster_id}" {{')
        lines.append(f'    label="{dataset}\\n{entity}";')
        lines.append('    style=rounded;')
        lines.append('    color="#bdc3c7";')
        lines.append('    fontsize=12;')
        lines.append("")

        for rid in sorted(rule_ids):
            rule = rules[rid]
            fn = rule.get("Function", "")
            shape = FUNCTION_SHAPES.get(fn, "box")
            colour = status_colour(rid)
            # Short label: just the numeric part + status
            short = rid.split("-", 2)[-1]  # e.g. "C-001-M"
            tooltip = rule.get("ValidationCriteria", {}).get("MustSatisfy", "")
            tooltip = tooltip.replace('"', '\\"')
            lines.append(
                f'    "{rid}" [label="{short}\\n{fn}", shape={shape}, '
                f'fillcolor="{colour}30", color="{colour}", tooltip="{tooltip}"];'
            )

        lines.append("  }")
        lines.append("")

    # Edges from composite rules to their children
    for rule_id, rule in rules.items():
        vc = rule.get("ValidationCriteria", {})
        deps = vc.get("Dependencies", [])
        if deps:
            for dep in deps:
                if dep in rules:
                    lines.append(f'  "{rule_id}" -> "{dep}";')

    # Legend
    lines.append("")
    lines.append('  subgraph cluster_legend {')
    lines.append('    label="Legend";')
    lines.append('    style=rounded;')
    lines.append('    color="#bdc3c7";')
    lines.append('    node [shape=box, fontsize=9];')
    lines.append(f'    leg_m [label="Mandatory (M)", fillcolor="{STATUS_COLOURS["M"]}30", color="{STATUS_COLOURS["M"]}"];')
    lines.append(f'    leg_c [label="Conditional (C)", fillcolor="{STATUS_COLOURS["C"]}30", color="{STATUS_COLOURS["C"]}"];')
    lines.append(f'    leg_o [label="Optional (O)", fillcolor="{STATUS_COLOURS["O"]}30", color="{STATUS_COLOURS["O"]}"];')
    lines.append('  }')
    lines.append("}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Visualize RM extraction output")
    parser.add_argument(
        "--input", "-i",
        default=str(Path(__file__).parent / "output"),
        help="Path to extraction output directory (default: extraction/output/)",
    )
    parser.add_argument(
        "--entity", "-e",
        help="Visualize a single entity (e.g. BilledCost). Default: all.",
    )
    parser.add_argument(
        "--format", "-f",
        default="png",
        choices=["png", "svg", "pdf"],
        help="Output format (default: png)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: extraction/output/rm_graph.<format>)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"Error: {input_dir} does not exist. Run the extractor first.", file=sys.stderr)
        sys.exit(1)

    rules = load_json_files(input_dir)
    if not rules:
        print("No rules found.", file=sys.stderr)
        sys.exit(1)

    # Filter to a single entity if requested
    if args.entity:
        rules = {k: v for k, v in rules.items() if v.get("EntityId") == args.entity}
        if not rules:
            print(f"No rules found for entity '{args.entity}'.", file=sys.stderr)
            sys.exit(1)
        title = f"Requirements Model — {args.entity}"
    else:
        title = "Requirements Model (all entities)"

    dot = build_dot(rules, title)

    out_path = args.output or str(input_dir / f"rm_graph.{args.format}")
    dot_path = out_path + ".dot"

    with open(dot_path, "w") as f:
        f.write(dot)

    try:
        subprocess.run(
            ["dot", f"-T{args.format}", dot_path, "-o", out_path],
            check=True,
        )
        print(f"Graph written to {out_path}")
        # Clean up dot source
        os.remove(dot_path)
    except FileNotFoundError:
        print("Error: 'dot' command not found. Install graphviz: brew install graphviz", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
