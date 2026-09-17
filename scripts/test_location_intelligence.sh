#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$repo_root" python3 -m unittest discover -s "$repo_root/tests" -p 'test_location_intelligence.py' -v
