"""
ddl_lineage.cli
===============
Argument parsing and output dispatch for the command-line interface.
"""

from __future__ import annotations

import argparse
import sys

from .analyzer import DDLLineageAnalyzer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ddl_lineage",
        description="DDL Lineage Analyzer v2 — extract data lineage from SQL DDL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # Plain-text report
  python -m ddl_lineage schema.sql

  # Graphviz DOT → SVG
  python -m ddl_lineage schema.sql -f dot | dot -Tsvg -o lineage.svg

  # Mermaid diagram
  python -m ddl_lineage schema.sql -f mermaid

  # JSON (machine-readable)
  python -m ddl_lineage schema.sql -f json -o lineage.json

  # Impact analysis for a specific object
  python -m ddl_lineage schema.sql --impact orders

  # Read from stdin
  cat schema.sql | python -m ddl_lineage -
""",
    )
    parser.add_argument(
        "input", nargs="?", default="-",
        help="DDL file path.  Use '-' or omit to read from stdin.",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "dot", "mermaid"],
        default="text",
        metavar="FMT",
        help="Output format: text (default), json, dot, mermaid",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Write output to FILE instead of stdout",
    )
    parser.add_argument(
        "--impact",
        metavar="OBJECT",
        help="Show upstream / downstream impact for a specific database object",
    )
    parser.add_argument(
        "--topo",
        action="store_true",
        help="Print topological order of objects (dependencies first) and exit",
    )
    parser.add_argument(
        "--cycles",
        action="store_true",
        help="Only report circular dependencies and exit",
    )

    args = parser.parse_args(argv)

    # ── Read input ──────────────────────────────────────────────────────────
    try:
        if args.input == "-":
            ddl = sys.stdin.read()
        else:
            with open(args.input, encoding="utf-8") as fh:
                ddl = fh.read()
    except FileNotFoundError:
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error reading input: {exc}", file=sys.stderr)
        return 1

    # ── Analyse ─────────────────────────────────────────────────────────────
    analyzer = DDLLineageAnalyzer()
    result = analyzer.analyze(ddl)

    # ── Special modes ────────────────────────────────────────────────────────

    if args.impact:
        imp = analyzer.impact(args.impact)
        _write(imp.summary(), args.output)
        return 0

    if args.topo:
        _write(" -> ".join(result["topo_order"]), args.output)
        return 0

    if args.cycles:
        if not result["cycles"]:
            _write("No circular dependencies detected.", args.output)
            return 0
        lines = [f"Found {len(result['cycles'])} cycle(s):"]
        for cyc in result["cycles"]:
            lines.append("  " + " -> ".join(cyc))
        _write("\n".join(lines), args.output)
        return int(bool(result["cycles"]))   # exit 1 if cycles found

    # ── Standard output ──────────────────────────────────────────────────────

    renderers = {
        "text":    analyzer.to_text,
        "json":    analyzer.to_json,
        "dot":     analyzer.to_dot,
        "mermaid": analyzer.to_mermaid,
    }
    out = renderers[args.format](result)
    _write(out, args.output)
    return 0


def _write(text: str, path: str | None) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Written to {path}", file=sys.stderr)
    else:
        print(text)
