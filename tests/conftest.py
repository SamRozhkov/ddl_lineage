"""
tests/conftest.py
-----------------
Ensure the package root is on sys.path when running pytest directly.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
