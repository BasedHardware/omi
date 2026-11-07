import re
with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

# Make sure imports are valid (e.g. pytest is imported at top)
content = "import pytest\n" + content.replace("import pytest\n", "")

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
