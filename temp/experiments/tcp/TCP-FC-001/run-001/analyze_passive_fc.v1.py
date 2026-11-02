#!/usr/bin/env python3
"""Preserved copy of the original passive analyzer.

This wrapper simply loads and executes the original ``analyze_passive_fc.py``
script.  It exists so that the original implementation is retained unchanged
while we iterate on a corrected version (still named ``analyze_passive_fc.py``).
"""

import importlib.util
import os
import sys


def main() -> None:
    # Resolve the path to the original analyzer (same directory).
    script_path = os.path.join(os.path.dirname(__file__), "analyze_passive_fc.py")
    if not os.path.isfile(script_path):
        sys.stderr.write(f"ERROR: original analyzer not found at {script_path}\n")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("original_analyzer", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Run its main() if present.
    if hasattr(module, "main"):
        module.main()
    else:
        sys.stderr.write("ERROR: original analyzer has no main() function.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
