"""Compatibility test entry; original-game import has been removed."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name("test_pinganzhi_sync.py")), run_name="__main__")
