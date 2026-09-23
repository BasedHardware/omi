import os

def create_agent_quickstart_ga(output_dir: str = "sdks/python-cli/examples") -> str:
    """
    Creates the Irish (ga) localization for the LLM/Agent quickstart guide.
    """
    os.makedirs(output_dir, exist_ok=True, mode=0o755)
    file_path = os.path.join(output_dir, "agent_quickstart.ga.md")
    
    content = """# Treoir Mhear Tionscnaimh Gníomhaire AI (Agent Quickstart)

Fáilte go dtí an treoir mhear, atá dírithe ar ghníomhairí, chun tosú le `omi-cli`.

## Reachtáil an Gníomhaire

```bash
omi-cli agent run --model gpt-4
```

## Cumraíocht

Féach ar an comhad `README.md` le haghaidh tuilleadh eolais.
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Also update or ensure README.md references it
    readme_path = os.path.join(output_dir, "README.md")
    readme_entry = "- [Irish (ga)](agent_quickstart.ga.md)\n"
    
    existing_readme = ""
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            existing_readme = f.read()
            
    if "agent_quickstart.ga.md" not in existing_readme:
        with open(readme_path, "a", encoding="utf-8") as f:
            f.write(readme_entry)
            
    return file_path
