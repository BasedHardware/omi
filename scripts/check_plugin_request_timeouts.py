<content>
#!/usr/bin/env python3

import ast
import os
import sys
from pathlib import Path

PLUGIN_DIR = Path("plugins")
REQUEST_TIMEOUT_PATTERN = "requests."
REQUESTS_WITHOUT_TIMEOUT = 0
REQUESTS_ON_EVENT_LOOP = 0

def is_async_function(node):
    """Check if a node is an async function definition."""
    return isinstance(node, ast.AsyncFunctionDef)

def check_for_requests_calls(tree, filepath):
    """Check for requests calls without timeout in the AST."""
    global REQUESTS_WITHOUT_TIMEOUT, REQUESTS_ON_EVENT_LOOP
    
    for node in ast.walk(tree):
        # Check for calls to requests module
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute) and 
                isinstance(node.func.value, ast.Name) and 
                node.func.value.id == "requests"
            ):
                # Check if 'timeout' is a keyword argument
                has_timeout = any(
                    kw.arg == "timeout" for kw in node.keywords
                )
                
                if not has_timeout:
                    REQUESTS_WITHOUT_TIMEOUT += 1
                    # Check if this is inside an async function
                    parent = node.parent
                    is_in_async = False
                    while parent:
                        if isinstance(parent, ast.AsyncFunctionDef):
                            is_in_async = True
                            break
                        parent = getattr(parent, 'parent', None)
                    
                    if is_in_async:
                        REQUESTS_ON_EVENT_LOOP += 1
                        print(f"  - {filepath}:{node.lineno} - Event loop blocking call")

def add_parent_info(node, parent=None):
    """Recursively add parent information to AST nodes."""
    node.parent = parent
    for child in ast.iter_child_nodes(node):
        add_parent_info(child, node)

def check_file(filepath):
    """Check a single Python file for requests calls without timeout."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(filepath))
        add_parent_info(tree)
        check_for_requests_calls(tree, filepath)
        
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}")
    except Exception as e:
        print(f"Error processing {filepath}: {e}")

def main():
    """Main function to check all Python files in the plugins directory."""
    if not PLUGIN_DIR.exists():
        print(f"Error: Plugin directory '{PLUGIN_DIR}' not found.")
        sys.exit(1)
    
    print("Checking plugins for requests calls without timeout...")
    print("=" * 60)
    
    for py_file in PLUGIN_DIR.rglob("*.py"):
        check_file(py_file)
    
    print("=" * 60)
    print(f"Total requests without timeout: {REQUESTS_WITHOUT_TIMEOUT}")
    print(f"Requests on event loop: {REQUESTS_ON_EVENT_LOOP}")
    
    if REQUESTS_WITHOUT_TIMEOUT > 0:
        print("\nFound requests calls without timeout. Please add timeout parameter.")
        sys.exit(1)
    else:
        print("\nAll requests calls have timeout parameters.")
        sys.exit(0)

if __name__ == "__main__":
    main()
</content>