"""Test configuration — ensure src modules are importable."""
import sys
from pathlib import Path

# Add project root to path so `from src.xxx import` works
sys.path.insert(0, str(Path(__file__).parent.parent))
