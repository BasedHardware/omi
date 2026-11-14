with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'r') as f:
    content = f.read()

import re
content = re.sub(
    r'with pytest.raises\(ValueError, match="unknown configuration"\):\s+qualify.evaluate_gate',
    r'with pytest.raises(ValueError, match="unknown configuration"):\n        qualify.evaluate_gate',
    content
)
content = re.sub(
    r'with pytest.raises\(RuntimeError, match="CUDA"\):\s+qualify.run',
    r'with pytest.raises(RuntimeError, match="CUDA"):\n        qualify.run',
    content
)
content = re.sub(
    r'with pytest.raises\(RuntimeError, match="flight packing refused this model layout"\):\s+qualify.run',
    r'with pytest.raises(RuntimeError, match="flight packing refused this model layout"):\n        qualify.run',
    content
)

with open('backend/tests/unit/test_batch_pipeline_flight_qualify.py', 'w') as f:
    f.write(content)
