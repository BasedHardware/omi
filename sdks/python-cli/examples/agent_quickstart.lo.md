# omi-cli ສໍາລັບເອເຈັນ (Lao / ພາສາລາວ)

> ຄູ່ມືພາກປະຕິບັດສໍາລັບລະບົບທີ່ຂັບເຄື່ອນດ້ວຍ LLM (Claude Code, Cursor, ບັອດຂອງທ່ານເອງ).

## ເປັນຫຍັງ CLI ຈຶ່ງເໝາະກັບເອເຈັນ (Why the CLI is agent-friendly)

* **ຂໍ້ຕົກລົງ JSON ທີ່ໝັ້ນຄົງ (Stable JSON contract).** `--json` ສົ່ງອອກເອກະສານ JSON ທີ່ຖືກຕ້ອງໄປຍັງ stdout ແລະ *ພຽງແຕ່* ເອກະສານ JSON ເທົ່ານັ້ນ — ບໍ່ມີຂໍ້ຄວາມຄວາມຄືບໜ້າ, ບໍ່ມີຕົວໝູນ. ຂໍ້ຜິດພາດຈະສົ່ງໄປທີ່ stderr ເປັນ `{"error": "...", "detail": "..."}`.
* **ລະຫັດອອກທີ່ໝັ້ນຄົງ (Stable exit codes).** `0` ສຳເລັດ / `1` ການໃຊ້ງານຜິດພາດ / `2` ການຢືນຢັນຕົວຕົນຜິດພາດ / `3` ເຊີບເວີຜິດພາດ / `4` ຈຳກັດອັດຕາ (rate limited) / `5` ບໍ່ພົບ. ເອເຈັນສາມາດຕັດສິນໃຈຕາມລະຫັດເຫຼົ່ານີ້ໄດ້ໂດຍບໍ່ຕ້ອງແປຂໍ້ຄວາມພາສາທຳມະຊາດ.
* **ບໍ່ມີການຖາມໂຕ້ຕອບໃນສະພາບແວດລ້ອມແບບ headless (No interactive prompts in headless contexts).** ໃຊ້ `--yes` (ຫຼື `-y`) ສໍາລັບຄໍາສັ່ງທີ່ມີການລຶບ ຫຼື ປ່ຽນແປງ; ໃຊ້ `--api-key` ຫຼື ຕັ້ງຄ່າ `OMI_API_KEY` ເພື່ອຂ້າມການເຂົ້າສູ່ລະບົບແບບໂຕ້ຕອບ.
* **ພຶດຕິກໍາການລອງໃໝ່ທີ່ຍືດຍຸ່ນ (Forgiving retry behavior).** ຂໍ້ຜິດພາດ `429` ແລະ `5xx` ຈະຖືກລອງໃໝ່ໂດຍອັດຕະໂນມັດພ້ອມກັບ backoff ກ່ອນທີ່ຈະແຈ້ງເຕືອນ.

## ການຢືນຢັນຕົວຕົນ (Auth - ຄັ້ງດຽວ, ໂດຍມະນຸດ)

ຜູ້ໃຊ້ຈະໄດ້ຮັບ API key ສຳລັບນັກພັດທະນາຈາກເວັບແອັບ Omi (`https://app.omi.me` → Developer → API Keys) ແລະ ເລືອກວິທີໃດໜຶ່ງ:

```bash
omi auth login                          # ວາງແບບໂຕ້ຕອບ; key ຈະບໍ່ຢູ່ໃນປະຫວັດ shell
# ຫຼື
export OMI_API_KEY=omi_dev_...          # ຊົ່ວຄາວ, ເໝາະສໍາລັບ container
```

## 5 ສິ່ງທີ່ເອເຈັນເຮັດຫຼາຍທີ່ສຸດ (The five things agents do most)

### 1. ອ່ານຄວາມຊົງຈໍາ (Read memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ສ້າງຄວາມຊົງຈໍາ (Create a memory)

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ອ່ານການສົນທະນາ (Read conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ອ່ານລາຍການທີ່ຕ້ອງເຮັດທີ່ຍັງຄ້າງ (Read open action items)

```bash
omi action-item list --json --open
```

### 5. ໝາຍລາຍການທີ່ຕ້ອງເຮັດວ່າສໍາເລັດແລ້ວ (Mark an action item done)

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API ທ້ອງຖິ່ນ (Local Desktop API)

ເມື່ອ Omi Desktop ເປີດໃຊ້ງານ API ທ້ອງຖິ່ນ, ເອເຈັນສາມາດສອບຖາມປະຫວັດໜ້າຈໍໃນອຸປະກອນ, ສະຫຼຸບ, SQL, ແລະ ວຽກຕ່າງໆ ໂດຍບໍ່ຕ້ອງໃຊ້ cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ຫຼື, ສໍາລັບເຊດຊັນຊົ່ວຄາວ:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

ພຽງແຕ່ເຮັດສຳເລັດ ຫຼື ລຶບວຽກ ເມື່ອຜູ້ໃຊ້ຮ້ອງຂໍຢ່າງຈະແຈ້ງເທົ່ານັ້ນ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ຈະຂຽນຮູບໜ້າຈໍລົງໃນດິສກ໌ ແລະ ຍັງຄົງພິມ JSON ອອກທາງ stdout ສຳລັບສະຄຣິບ. ປົກກະຕິແລ້ວ ID ຮູບໜ້າຈໍຈະມາຈາກ `local search-screen` ຫຼື SQL ເທິງຕາຕະລາງ `screenshots`. ຖ້າ Desktop ສົ່ງຄືນຂໍ້ຜິດພາດທີ່ມີໂຄງສ້າງເຊັ່ນ `screenshot_pending`, `screenshot_file_missing`, ຫຼື `screenshot_chunk_corrupted`, ໂໝດ JSON ຈະຮັກສາຊ່ອງຂໍ້ມູນ `reason`, `hint`, ແລະ `screenshot_id` ໄວ້ໃນ stderr ເພື່ອໃຫ້ເອເຈັນສາມາດລອງໃໝ່ກັບ ID ເກົ່າ ຫຼື ລາຍງານບັນຫາທີ່ແນ່ນອນໄດ້. ກວດສອບຜົນຜະລິດທີ່ສຳເລັດດ້ວຍ `file PATH` ກ່ອນທີ່ຈະສົ່ງໄປຍັງເຄື່ອງມື vision.

## ຕົວຢ່າງການເຮັດວຽກ: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ການຈັດການ Rate Limits (Handling rate limits)

ຄວາມຊົງຈໍາ: 120/ຊມ. ການສົນທະນາ: 25/ຊມ. ສ້າງເປັນກຸ່ມ: 15/ຊມ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ຄຳແນະນຳ (Tips)

* ໃຊ້ `--profile <name>` ຖ້າເອເຈັນຂອງທ່ານຈັດການບັນຊີ Omi ຫຼາຍບັນຊີ. ແຕ່ລະໂປຣໄຟລ໌ມີຂໍ້ມູນປະຈຳຕົວ ແລະ API base ຂອງຕົນເອງ.
* ໃຊ້ `--api-base http://localhost:8080` ສຳລັບການທົດສອບ backend ໃນເຄື່ອງ.
* ໃຊ້ `OMI_LOCAL_API_URL` ແລະ `OMI_LOCAL_TOKEN` ເພື່ອແທນທີ່ການຕັ້ງຄ່າ Desktop API ສະເພາະໂປຣໄຟລ໌ສຳລັບການຮັນຄັ້ງດຽວ.
* ໃຊ້ `--verbose` ສຳລັບການດີບັກ — ມັນຈະບັນທຶກ `METHOD path → status (Ns)` ໄປຍັງ stderr ໂດຍບໍ່ກະທົບຕໍ່ stdout, ດັ່ງນັ້ນໂໝດ JSON ຈຶ່ງຍັງໃຊ້ງານໄດ້.
* ສຳລັບການສົ່ງເນື້ອຫາເຂົ້າໄປໃນການສົນທະນາ (pipe), ໃຫ້ໃຊ້ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
