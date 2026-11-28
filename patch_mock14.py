with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

import re
content = re.sub(
    r'import subprocess\n    import sys',
    r'import subprocess\n    import sys\n    sys.modules.pop("diarizer.batch_pipeline_flight_qualify", None)',
    content
)

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
