"""Validate a Colosseum result directory and print a machine-readable report."""

from __future__ import annotations

import sys

from beyond_confessions.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["validate-results", *sys.argv[1:]]))
