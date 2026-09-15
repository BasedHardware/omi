# omi-cli Huong dan nhanh tieng Viet

> Noi chuyen voi Omi tu terminal. Danh cho con nguoi **va** AI agent.

`omi-cli` la giao dien dong lenh cho API nha phat trien [Omi](https://omi.me).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Tai lieu:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)

---

## 1. Cai dat

```bash
pipx install omi-cli
# hoac
pip install omi-cli
```

> **Luu y:** Ten goi PyPI la `omi-cli`. Lenh la `omi`.

```bash
omi --version
omi --help
```

---

## 2. Xac thuc

| Cach | Ung dung | Lenh |
| :--- | :--- | :--- |
| **API Key** | CI/CD, Agent | `omi auth login --api-key ...` |
| **Trinh duyet** | Ca nhan | `omi auth login --browser` |

```bash
omi auth login
# 1) Browser → Dang nhap Google hoac Apple
# 2) API key → Dan key tu app.omi.me
```

### Dang nhap bang API Key

Tu [app.omi.me](https://app.omi.me), vao **Developer → API Keys**.

```bash
omi auth login --api-key omi_dev_...
# hoac qua bien moi truong
export OMI_API_KEY=omi_dev_...
```

### Kiem tra trang thai

```bash
omi auth status    # Trang thai cuc bo
omi auth whoami    # Xac minh phia server
```

---

## 3. Doc du lieu

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

| Lenh | Mo ta |
| --- | --- |
| `memory` | Su kien va ky niem |
| `conversation` | Cuoc hoi thoai |
| `action-item` | Cong viec |
| `goal` | Muc tieu |

---

## 4. JSON cho script

```bash
omi --json memory list --limit 5 | jq '.[] | {id, content}'
```

### Trong shell script

```bash
ids=$(omi --json memory list --limit 5 | jq -r '.[].id')
for id in $ids; do
  echo "Dang xu ly: $id"
done
```

### Trong Python

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

*Duoc tao boi AUTO (AI Agent). Bounty: Issue #13066*
