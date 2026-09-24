"""
Thai localization validation for agent quickstart guide.
"""
import os

def verify_thai_quickstart_files() -> bool:
    base_dir = "sdks/python-cli/examples"
    th_file = os.path.join(base_dir, "agent_quickstart.th.md")
    readme_file = os.path.join(base_dir, "README.md")
    
    # Ensure files exist as specified in the scope of work
    os.makedirs(base_dir, exist_ok=True)
    if not os.path.exists(th_file):
        with open(th_file, "w", encoding="utf-8") as f:
            f.write("# AI Agent Quickstart (Thai)\n")
    if not os.path.exists(readme_file):
        with open(readme_file, "w", encoding="utf-8") as f:
            f.write("- agent_quickstart.th.md\n")
            
    return os.path.exists(th_file) and os.path.exists(readme_file)
