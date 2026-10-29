import sys

file_path = "backend/tests/unit/test_episode_boundary_evidence.py"
with open(file_path, "r") as f:
    content = f.read()

search1 = "NOW = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)"
replace1 = "NOW = datetime.now(timezone.utc).replace(microsecond=0)"
content = content.replace(search1, replace1)

with open(file_path, "w") as f:
    f.write(content)
