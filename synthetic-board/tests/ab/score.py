#!/usr/bin/env python3
"""Tally the synthetic-board A/B gate and emit pass / marginal / fail.

Thin runnable entry point; the logic lives in `sboard.ab_score` (typed + tested).

Usage:
    python tests/ab/score.py
    python tests/ab/score.py --runs-dir tests/ab/runs --master-dir tests/ab/master
"""

from __future__ import annotations

import sys

from sboard.ab_score import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
