```python
from dataclasses import dataclass
import yaml
from fire import Fire
from typing import List, Optional

@dataclass
class ActionItemsConfig:
    input_file: str = "action_items.yaml"
    output_file: str = "action_items.html"
    dark_mode: bool = True
    status_filter: Optional[str] = None

def main(config: ActionItemsConfig = None):
    if config is None:
        config = ActionItemsConfig()

    with open(config.input_file) as f:
        data = yaml.safe_load(f)
    
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Action Items</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white">
    <div class="container mx-auto p-4">
        <div class="flex items-center justify-between mb-4">
            <h1 class="text-2xl font-bold">Action Items</h1>
            <div class="flex items-center space-x-4">
                <button onclick="window.print()" class="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700">
                    Print
                </button>
            </div>
        </div>
        <div class="relative">
            <input type="text" id="searchInput" class="w-full p-2 border rounded" placeholder="Search...">
            <div id="results" class="mt-4 space-y-4">
                {items}
            </div>
        </div>
        <script>
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const searchQuery = e.target.value.toLowerCase();
            const results = document.getElementById('results');
            const elements = results.getElementsByClassName('action-item');
            
            for(let element of elements) {
                const text = element.textContent.toLowerCase();
                if(text.includes(searchQuery)) {
                    element.style.display = 'block';
                } else {
                    element.style.display = 'none';
                }
            }
        });
        </script>
    </div>
</body>
</html>"""

    items = []
    for item in data.get("action_items", []):
        items.append(f"""
        <div class="action-item p-4 bg-gray-800 rounded">
            <div class="flex justify-between items-center">
                <span class="font-bold">ID: {item['id']}</span>
                <span class="text-sm opacity-75">[{item['date']}]</span>
            </div>
            <div class="mt-2">
                <h3 class="font-semibold">"{item['title']}"</h3>
                <p class="text-sm text-gray-300">{item['description']}</p>
                <div class="mt-2 flex space-x-4">
                    <span class="px-2 py-1 rounded-full bg-blue-600/20 text-blue-300 text-xs">
                        {item['status']}
                    </span>
                    <span class="px-2 py-1 rounded-full bg-gray-700/20 text-gray-300 text-xs">
                        {item['priority']}
                    </span>
                </div>
            </div>
        </div>
        """)

    data = {"action_items": data.get("action_items", [])}
    with open(config.output_file, "w") as f:
        f.write(html_template.replace("{items}", "".join(items)))

if __name__ == "__main__":
    Fire(main)
```

```markdown
To generate an HTML dashboard from action items, use the following recipe:

```python
from dataclasses import dataclass
import yaml
from fire import Fire
from typing import List, Optional

@dataclass
class ActionItemsConfig:
    input_file: str = "action_items.yaml"
    output_file: str = "action_items.html"
    dark_mode: bool = True
    status_filter: Optional[str] = None

def main(config: ActionItemsConfig = None):
    if config is None:
        config = ActionItemsConfig()

    with open(config.input_file) as f:
        data = yaml.safe_load(f)
    
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Action Items</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white">
    <div class="container mx-auto p-4">
        <div class="flex items-center justify-between mb-4">
            <h1 class="text-2xl font-bold">Action Items</h1>
            <div class="flex items-center space-x-4">
                <button onclick="window.print()" class="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700">
                    Print
                </button>
            </div>
        </div>
        <div class="relative">
            <input type="text" id="searchInput" class="w-full p-2 border rounded" placeholder="Search...">
            <div id="results" class="mt-4 space-y-4">
                {items}
            </div>
        </div>
        <script>
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const searchQuery = e.target.value.toLowerCase();
            const results = document.getElementById('results');
            const elements = results.getElementsByClassName('action-item');
            
            for(let element of elements) {
                const text = element.textContent.toLowerCase();
                if(text.includes(searchQuery)) {
                    element.style.display = 'block';
                } else {
                    element.style.display = 'none';
                }
            }
        });
        </script>
    </div>
</body>
</html>"""

    items = []
    for item in data.get("action_items", []):
        items.append(f"""
        <div class="action-item p-4 bg-gray-800 rounded">
            <div class="flex justify-between items-center">
                <span class="font-bold">ID: {item['id']}</span>
                <span class="text-sm opacity-75">[{item['date']}]</span>
            </div>
            <div class="mt-2">
                <h3 class="font-semibold">"{item['title']}"</h3>
                <p class="text-sm text-gray-300">{item['description']}</p>
                <div class="mt-2 flex space-x-4">
                    <span class="px-2 py-1 rounded-full bg-blue-600/20 text-blue-300 text-xs">
                        {item['status']}
                    </span>
                    <span class="px-2 py-1 rounded-full bg-gray-700/20 text-gray-300 text-xs">
                        {item['priority']}
                    </span>
                </div>
            </div>
        </div>
        """)

    data = {"action_items": data.get("action_items", [])}
    with open(config.output_file, "w") as f:
        f.write(html_template.replace("{items}", "".join(items)))

if __name__ == "__main__":
    Fire(main)
```
```

```python
from dataclasses import dataclass
import yaml
from fire import Fire
from typing import List, Optional

@dataclass
class ActionItemsConfig:
    input_file: str = "action_items.yaml"
    output_file: str = "action_items.html"
    dark_mode: bool = True
    status_filter: Optional[str] = None

def test_action_items_to_html():
    config = ActionItemsConfig()
    with open(config.input_file) as f:
        data = yaml.safe_load(f)
    
    expected_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Action Items</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white">
    <div class="container mx-auto p-4">
        <div class="flex items-center justify-between mb-4">
            <h1 class="text-2xl font-bold">Action Items</h1>
            <div class="flex items-center space-x-4">
                <button onclick="window.print()" class="px-4 py-2 bg-blue-600 rounded hover:bg-blue-700">
                    Print
                </button>
            </div>
        </div>
        <div class="relative">
            <input type="text" id="searchInput" class="w-full p-2 border rounded" placeholder="Search...">
            <div id="results" class="mt-4 space-y-4">
                {items}
            </div>
        </div>
        <script>
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const searchQuery = e.target.value.toLowerCase();
            const results = document.getElementById('results');
            const elements = results.getElementsByClassName('action-item');
            
            for(let element of elements) {
                const text = element.textContent.toLowerCase();
                if(text.includes(searchQuery)) {
                    element.style.display = 'block';
                } else {
                    element.style.display = 'none';
                }
            }
        });
        </script>
    </div>
</body>
</html>"""
    
    with open(config.input_file) as f:
        data = yaml.safe_load(f)
    
    items = []
    for item in data.get("action_items", []):
        items.append(f"""
        <div class="action-item p-4 bg-gray-800 rounded">
            <div class="flex justify-between items-center">
                <span class="font-bold">ID: {item['id']}</span>
                <span class="text-sm opacity-75">[{item['date']}]</span>
            </div>
            <div class="mt-2">
                <h3 class="font-semibold">"{item['title']}"</h3>
                <p class="text-sm text-gray-300">{item['description']}</p>
                <div class="mt-2 flex space-x-4">
                    <span class="px-2 py-1 rounded-full bg-blue-600/20 text-blue-300 text-xs">
                        {item['status']}
                    </span>
                    <span class="px-2 py-1 rounded-full bg-gray-700/20 text-gray-300 text-xs">
                        {item['priority']}
                    </span>
                </div>
            </div>
        </div>
        """)

    expected_html = expected_html.replace("{items}", "".join(items))
    with open(config.output_file, "w") as f:
        f.write(expected_html)

    assert main() is None

if __name__ == "__main__":
    Fire(main)
```