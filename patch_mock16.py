with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

new_mock = """
def test_main_block_coverage_runpy():
    import runpy
    import sys
    import pytest
    from unittest.mock import patch

    with patch.object(sys, 'argv', ['diarizer.batch_pipeline_flight_qualify', '--help']):
        with pytest.raises(SystemExit):
            runpy.run_module('diarizer.batch_pipeline_flight_qualify', run_name='__main__')
"""

content += "\n" + new_mock.strip() + "\n"

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
