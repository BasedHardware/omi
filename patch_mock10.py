import re

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

# Add test for __main__ block
new_mock = """
def test_import_error_torch(monkeypatch):
    import sys
    import importlib

    # Force reload of module without torch
    monkeypatch.setitem(sys.modules, 'torch', None)

    import diarizer.batch_pipeline_flight_qualify
    importlib.reload(diarizer.batch_pipeline_flight_qualify)

    assert diarizer.batch_pipeline_flight_qualify.torch is None

    # Clean up and reload with torch
    monkeypatch.undo()
    importlib.reload(diarizer.batch_pipeline_flight_qualify)

def test_main_block():
    import subprocess
    import sys
    import os

    env = os.environ.copy()
    env['PYTHONPATH'] = '.'

    # We can run it and pass --help to make it exit immediately
    result = subprocess.run([sys.executable, 'diarizer/batch_pipeline_flight_qualify.py', '--help'], env=env, capture_output=True, text=True)
    assert result.returncode == 0
"""

content += "\n" + new_mock.strip() + "\n"

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
