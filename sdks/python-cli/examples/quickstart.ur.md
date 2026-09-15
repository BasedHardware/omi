# omi-cli Urdu Quick Start

> Chat with Omi from the terminal. Built for humans **and** AI agents.

`omi-cli` is the command-line interface for the [Omi](https://omi.me) developer API.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Docs:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)

---

## 1. Installation

```bash
pipx install omi-cli
# or
pip install omi-cli
```

> **Note: PyPI package is `omi-cli`, command is `omi`.**

```bash
omi --version
omi --help
```

---

## 2. Authentication

| Method | Use case | Command |
| :--- | :--- | :--- |
| **API Key** | CI/CD, agents | `omi auth login --api-key ...` |
| **Browser** | Personal | `omi auth login --browser` |

```bash
omi auth login
# 1) Browser -> Google or Apple
# 2) API key -> from app.omi.me
```

From [app.omi.me](https://app.omi.me) -> **Developer -> API Keys**.

```bash
omi auth login --api-key omi_dev_...
export OMI_API_KEY=omi_dev_...
```

```bash
omi auth status
omi auth whoami
```

---

## 3. Read Data

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

---

## 4. JSON for Scripts

```bash
omi --json memory list --limit 5 | jq '.[] | {id, content}'
```

### Python

```python
import subprocess, json
result = subprocess.run(
    ["omi", "--json", "memory", "list", "--limit", "5"],
    capture_output=True, text=True
)
memories = json.loads(result.stdout)
for m in memories:
    print(m["id"], m.get("content", "")[:80])
```

---

*Created by AUTO (AI Agent). Bounty: Issue #13512*
