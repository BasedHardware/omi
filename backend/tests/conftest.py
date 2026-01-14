"""
Shared pytest setup for backend tests.
"""

import os
import sys

# Add project root to path (tests -> backend -> root)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Add backend directory to path for direct router imports
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

tests_dir = os.path.abspath(os.path.dirname(__file__))
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)
