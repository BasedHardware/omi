import os

def create_quickstart_files(base_dir: str):
    examples_dir = os.path.join(base_dir, "sdks", "python-cli", "examples")
    os.makedirs(examples_dir, exist_ok=True)
    
    sl_path = os.path.join(examples_dir, "agent_quickstart.sl.md")
    sl_content = """# Hitri začetek z AI agentom (Slovenščina)\n\nDobrodošli v vodniku za hiter začetek uporabe AI agentov z `omi-cli`.\n\n## Namestitev\n\n```bash\npip install omi-cli\n```\n\n## Uporaba\n\nZa zagon agenta uporabite naslednji ukaz:\n\n```bash\nomi-cli agent --start\n```\n"""
    with open(sl_path, "w", encoding="utf-8") as f:
        f.write(sl_content)
        
    readme_path = os.path.join(examples_dir, "README.md")
    readme_content = "- [agent_quickstart.sl.md](agent_quickstart.sl.md) - Hitri začetek z AI agentom (Slovenščina)\n"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)

    return sl_path, readme_path
