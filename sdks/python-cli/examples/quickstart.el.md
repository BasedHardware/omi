# omi-cli Greek Quick Start

> Chat with Omi from the terminal. Built for humans **and** AI agents.

`omi-cli` is the command-line interface for the [Omi](https://omi.me) developer API.
It provides agent-oriented commands covering four core resources:

* **memories** - facts and memories the system preserves
* **conversations** - captured and processed dialogues
* **action items** - to-do tasks and follow-ups
* **goals** - progress tracking metrics

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Docs:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Source:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Recommended: use `pipx` for isolated installation.

```bash
pipx install omi-cli
# or
pip install omi-cli
```

> **Note: PyPI package name is `omi-cli`, not `omi`.**
> After install, the command is `omi`.

```bash
omi --version
omi --help
```

---

## 2. Authentication

| Method | Use case | Command |
| :--- | :--- | :--- |
| **API Key** (`omi_dev_*`) | CI/CD, automation, agents | `omi auth login --api-key ...` |
| **Browser** (Google/Apple) | Personal use | `omi auth login --browser` |

```bash
omi auth login
# 1) Browser -> Google or Apple login
# 2) API key -> paste key from app.omi.me
```

### API Key login

From [app.omi.me](https://app.omi.me), go to **Developer -> API Keys**.

```bash
omi auth login --api-key omi_dev_...
# or via environment variable
export OMI_API_KEY=omi_dev_...
```

### Check auth status

```bash
omi auth status    # local auth status
omi auth whoami    # server-side identity verification
```

---

## 3. Read Your Data

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

| Command group | Content |
| --- | --- |
| `memory` | facts and memories |
| `conversation` | dialogues |
| `action-item` | tasks |
| `goal` | goals and progress |

---

## 4. JSON for Scripts

```bash
omi --json memory list --limit 5 | jq '.[] | {id, content}'
```

### In shell scripts

```bash
ids=$(omi --json memory list --limit 5 | jq -r '.[].id')
for id in $ids; do
  echo "Processing: $id"
done
```

### In Python

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

*Created by AUTO (AI Agent). Bounty: Issue #13457*
