import sys
from pathlib import Path

# The toy simulation lives in prototype/ (not an installed package); make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "prototype"))
