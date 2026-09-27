import re

with open("backend/scripts/generate_dart_models.py", "r") as f:
    content = f.read()

pattern = r"""    'conversation': \{
        'output': DEFAULT_OUTPUT_DIR / 'conversation_wire\.g\.dart',
        'schemas': \("""
replacement = """    'conversation': {
        'output': DEFAULT_OUTPUT_DIR / 'conversation_wire.g.dart',
        'schemas': (
            'StatusResponse',"""

new_content = re.sub(pattern, replacement, content)
with open("backend/scripts/generate_dart_models.py", "w") as f:
    f.write(new_content)
