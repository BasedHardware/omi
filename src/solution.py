"""Welsh CLI Quickstart Documentation Helper."""

import os

GUIDE_FILENAME = "agent_quickstart.cy.md"
README_FILENAME = "README.md"

def get_welsh_quickstart_content() -> str:
    """Return the content of the Welsh agent quickstart guide."""
    return (
        "# Cyflym-ddechreuad Asiant LLM\n\n"
        "Croeso i ganllaw cyflym-ddechreuad asiant LLM omi-cli.\n"
        "## Gosod\n"
        "Defnyddiwch y gorchymyn canlynol i osod y CLI:\n"
        "```bash\n"
        "pip install omi-cli\n"
        "```\n"
    )

def get_readme_content() -> str:
    """Return the content of the examples README including the Welsh guide."""
    return (
        "# Examples\n\n"
        "- [English Quickstart](agent_quickstart.md)\n"
        "- [Welsh Quickstart](agent_quickstart.cy.md)\n"
    )

def register_welsh_guide(base_path: str = "sdks/python-cli/examples") -> None:
    """Create the Welsh quickstart guide and update the README."""
    os.makedirs(base_path, exist_ok=True)
    
    guide_path = os.path.join(base_path, GUIDE_FILENAME)
    with open(guide_path, "w", encoding="utf-8") as f:
        f.write(get_welsh_quickstart_content())
        
    readme_path = os.path.join(base_path, README_FILENAME)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(get_readme_content())
