import sys
from pathlib import Path

here = Path(__file__).parent
sys.path.insert(0, str(here))
sys.path.insert(0, str(here.parent / "src"))
