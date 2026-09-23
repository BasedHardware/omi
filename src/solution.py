import os

def create_icelandic_quickstart():
    docs_dir = 'sdks/python-cli/examples'
    os.makedirs(docs_dir, exist_ok=True)
    
    content = """# Fljótleg byrjun fyrir gervigreindarumboð (Agent Quickstart)\n\nVelkomin(n) í fljótlegu byrjunarleiðbeiningarnar fyrir OMI CLI.\n\n## Uppsetning\n\n```bash\npip install omi-cli\n```\n\n## Notkun\n\n```bash\nomi-cli agent --help\n```\n"""
    
    file_path = os.path.join(docs_dir, 'agent_quickstart.is.md')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    readme_path = os.path.join(docs_dir, 'README.md')
    readme_entry = "- [Icelandic (is)](agent_quickstart.is.md)\n"
    
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_content = f.read()
        if 'agent_quickstart.is.md' not in readme_content:
            with open(readme_path, 'a', encoding='utf-8') as f:
                f.write(readme_entry)
    else:
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(f"# Examples\n\n{readme_entry}")

if __name__ == '__main__':
    create_icelandic_quickstart()
