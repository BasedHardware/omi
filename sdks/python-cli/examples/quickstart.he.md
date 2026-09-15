# omi-cli madrikh hitkhayrut be-Ivrit

> Daber im Omi mi-ha-terminal. Mutar le-benei adam ve-suchnim AI.

`omi-cli` hu mimsak ha-pekuda le-API ha-mefatkhim shel [Omi](https://omi.me).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Teud:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)

---

## 1. Hatkana

```bash
pipx install omi-cli
# o
pip install omi-cli
```

> **Heara:** Shem ha-chavila hu `omi-cli`. Ha-pekuda hi `omi`.

```bash
omi --version
omi --help
```

---

## 2. Hitabdut

| Shita | Yamim | Pekuda |
| :--- | :--- | :--- |
| **API Key** | CI/CD, Agentim | `omi auth login --api-key ...` |
| **Browser** | Ishi | `omi auth login --browser` |

```bash
omi auth login
# 1) Browser → Google o Apple
# 2) API key → Mafteach me-app.omi.me
```

### API Key

Me-[app.omi.me](https://app.omi.me), Developer → API Keys.

```bash
omi auth login --api-key omi_dev_...
# o via mishtane sviva
export OMI_API_KEY=omi_dev_...
```

### Bedikat status

```bash
omi auth status
omi auth whoami
```

---

## 3. Kriat netunim

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

---

## 4. JSON le-skriptim

```bash
omi --json memory list --limit 5 | jq '.[] | {id, content}'
```

---

*Noctar al yedei AUTO (AI Agent). Bounty: Issue #13160*
