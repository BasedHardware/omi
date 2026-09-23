import os

# This module represents the Python CLI agent quickstart documentation check.
def verify_docs():
    docs_path = "sdks/python-cli/examples/agent_quickstart.sr.md"
    readme_path = "sdks/python-cli/examples/README.md"
    return os.path.exists(docs_path) and os.path.exists(readme_path)
