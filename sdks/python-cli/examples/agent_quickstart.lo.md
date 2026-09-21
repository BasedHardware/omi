# omi-cli ສຳລັບຕົວແທນ (Agents)

> ຄູ່ມືພາກປະຕິບັດສຳລັບລະບົບທີ່ຂັບເຄື່ອນດ້ວຍ LLM (Claude Code, Cursor, ບັອດສ່ວນຕົວຂອງທ່ານ).

## ເປັນຫຍັງ CLI ຈຶ່ງເໝາະສົມກັບຕົວແທນ

* **ຂໍ້ກຳນົດ JSON ທີ່ໝັ້ນຄົງ.** `--json` ຈະສົ່ງອອກເອກະສານ JSON ທີ່ຖືກຕ້ອງໄປຍັງ stdout
  ແລະມີ *ພຽງແຕ່* ເອກະສານ JSON ເທົ່ານັ້ນ — ບໍ່ມີຂໍ້ຄວາມຄວາມຄືບໜ້າ ຫຼື ພາບເຄື່ອນໄຫວໂຫຼດ.
  ຂໍ້ຜິດພາດຈະຖືກສົ່ງໄປຍັງ stderr ໃນຮູບແບບ `{"error": "...", "detail": "..."}`.
* **ລະຫັດອອກ (exit codes) ທີ່ໝັ້ນຄົງ.** `0` ສຳເລັດ / `1` ການນຳໃຊ້ຜິດພາດ / `2` ການຢືນຢັນຕົວຕົນຜິດພາດ /
  `3` ເຊີເວີຜິດພາດ / `4` ເກີນຂີດຈຳກັດຄຳຂໍ (rate limited) / `5` ບໍ່ພົບ. ຕົວແທນສາມາດຕັດສິນໃຈ
  ຕາມລະຫັດເຫຼົ່ານີ້ໄດ້ໂດຍບໍ່ຕ້ອງແຍກວິເຄາະຂໍ້ຜິດພາດທາງພາສາທຳມະຊາດ.
* **ບໍ່ມີການຖາມໂຕ້ຕອບໃນສະພາບແວດລ້ອມແບບ headless.** ໃສ່ `--yes` (ຫຼື `-y`) ສຳລັບຄຳສັ່ງທີ່ປ່ຽນແປງຂໍ້ມູນ;
  ໃສ່ `--api-key` ຫຼື ຕັ້ງຄ່າຕົວປ່ຽນ `OMI_API_KEY` ເພື່ອຂ້າມການເຂົ້າສູ່ລະບົບແບບໂຕ້ຕອບ.
* **ພຶດຕິກຳການລອງໃໝ່ທີ່ຍືດຫຍຸ່ນ.** ຂໍ້ຜິດພາດ `429` ແລະ `5xx` ຈະຖືກລອງໃໝ່ໂດຍອັດຕະໂນມັດພ້ອມການລໍຖ້າ (backoff)
  ກ່ອນທີ່ຈະສະແດງອອກມາ.

## ການຢືນຢັນຕົວຕົນ (ເຮັດຄັ້ງດຽວໂດຍມະນຸດ)

ຜູ້ໃຊ້ຮັບເອົາ API key ສຳລັບນັກພັດທະນາຈາກເວັບແອັບ Omi
(`https://app.omi.me` → Developer → API Keys) ແລະ ເລືອກຢ່າງໃດຢ່າງໜຶ່ງ:

```bash
omi auth login                          # ວາງແບບໂຕ້ຕອບ; ຄີຈະບໍ່ບັນທຶກລົງໃນປະຫວັດ shell
# ຫຼື
export OMI_API_KEY=omi_dev_...          # ຊົ່ວຄາວ, ສະດວກສຳລັບ container
```

## ຫ້າສິ່ງທີ່ຕົວແທນເຮັດເລື້ອຍທີ່ສຸດ

### 1. ອ່ານຄວາມຊົງຈຳ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ສ້າງຄວາມຊົງຈຳ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ອ່ານບົດສົນທະນາ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ອ່ານລາຍການວຽກທີ່ຍັງເປີດຢູ່

```bash
omi action-item list --json --open
```

### 5. ໝາຍລາຍການວຽກວ່າສຳເລັດ

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API ພາຍໃນເຄື່ອງ (Local Desktop API)

ເມື່ອ Omi Desktop ເປີດໃຊ້ API ພາຍໃນເຄື່ອງ, ຕົວແທນສາມາດສອບຖາມປະຫວັດໜ້າຈໍໃນອຸປະກອນ,
ບົດສະຫຼຸບ, ຂໍ້ມູນ SQL ແລະ ວຽກງານໄດ້ໂດຍບໍ່ຕ້ອງໃຊ້ cloud developer API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ຫຼື ສຳລັບເຊດຊັນຊົ່ວຄາວ:
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

ເຮັດວຽກໃຫ້ສຳເລັດ ຫຼື ລຶບວຽກສະເພາະເມື່ອຜູ້ໃຊ້ຮ້ອງຂໍຢ່າງຈະແຈ້ງເທົ່ານັ້ນ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ຈະບັນທຶກພາບໜ້າຈໍລົງດິດ ແລະ
ຍັງຄົງສະແດງ JSON ໄປຍັງ stdout ສຳລັບສະຄຣິບ. ລະຫັດພາບໜ້າຈໍມັກຈະມາຈາກ `local search-screen`
ຫຼື ຄຳຖາມ SQL ເທິງຕາຕະລາງ `screenshots`. ຖ້າ Desktop ສົ່ງຄືນຂໍ້ຜິດພາດທີ່ມີໂຄງສ້າງເຊັ່ນ
`screenshot_pending`, `screenshot_file_missing` ຫຼື `screenshot_chunk_corrupted` ຮູບແບບ JSON
ຈະຮັກສາຊ່ອງ `reason`, `hint` ແລະ `screenshot_id` ໄວ້ໃນ stderr ເພື່ອໃຫ້ຕົວແທນສາມາດລອງໃໝ່ດ້ວຍ ID ເກົ່າ
ຫຼື ລາຍງານອຸປະສັກໄດ້ຢ່າງຊັດເຈນ. ກວດສອບຜົນໄດ້ຮັບທີ່ສຳເລັດດ້ວຍ `file PATH` ກ່ອນສົ່ງຕໍ່ໄປຍັງເຄື່ອງມືປະມວນຜົນພາບ.

## ຕົວຢ່າງການເຮັດວຽກ: ຮອບວຽນຕົວແທນ Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """ເອີ້ນໃຊ້ omi CLI ໃນໂໝດ JSON, ແຈ້ງຂໍ້ຜິດພາດຫາກລະຫັດອອກບໍ່ສຳເລັດ."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ຈະສະແດງຂໍ້ຜິດພາດທີ່ມີໂຄງສ້າງໄປຍັງ stderr ໃນໂໝດ JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# ອ່ານທຸກລາຍການວຽກທີ່ເປີດຢູ່ ແລະ ໝາຍລາຍການທີ່ເກົ່າກວ່າ 30 ວັນວ່າສຳເລັດ.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ການຈັດການຂີດຈຳກັດຄຳຂໍ (Rate Limits)

ຄວາມຊົງຈຳ: 120/ຊົ່ວໂມງ. ບົດສົນທະນາ: 25/ຊົ່ວໂມງ. ການສ້າງແບບກຸ່ມ: 15/ຊົ່ວໂມງ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ເກີນຂີດຈຳກັດ
    err = json.loads(result.stderr)
    # err["detail"] ຈະມີລັກສະນະ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ຄຳແນະນຳທີ່ເປັນປະໂຫຍດ

* ໃຊ້ `--profile <name>` ຖ້າຕົວແທນຂອງທ່ານຈັດການບັນຊີ Omi ຫຼາຍບັນຊີ.
  ແຕ່ລະໂປຣໄຟລ໌ຈະມີຂໍ້ມູນປະຈຳຕົວ ແລະ ຖານ API ຂອງຕົນເອງ.
* ໃຊ້ `--api-base http://localhost:8080` ສຳລັບການທົດສອບເຊີເວີພາຍໃນເຄື່ອງ.
* ໃຊ້ `OMI_LOCAL_API_URL` ແລະ `OMI_LOCAL_TOKEN` ເພື່ອແທນທີ່ການຕັ້ງຄ່າ Desktop API ພາຍໃນເຄື່ອງສຳລັບການລັນຄັ້ງດຽວ.
* ໃຊ້ `--verbose` ສຳລັບການດີບັກ — ມັນຈະບັນທຶກ `METHOD path → status (Ns)` ໄປຍັງ stderr
  ໂດຍບໍ່ກະທົບຕໍ່ stdout, ດັ່ງນັ້ນໂໝດ JSON ຈຶ່ງຍັງໃຊ້ງານໄດ້ຢ່າງຖືກຕ້ອງ.
* ສຳລັບການສົ່ງເນື້ອຫາເຂົ້າໃນບົດສົນທະນາ ໃຫ້ໃຊ້ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
