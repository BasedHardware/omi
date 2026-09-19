# omi-cli pour les agents

> Guide pratique pour les environnements pilotés par LLM (Claude Code, Cursor, vos propres robots).

## Pourquoi la CLI est adaptée aux agents

* **Contrat JSON stable.** `--json` émet un document JSON valide sur stdout et
  *uniquement* un document JSON — aucun message de progression, aucune animation d'attente. Les erreurs sont envoyées sur
  stderr sous la forme `{"error": "...", "detail": "..."}`.
* **Codes de sortie stables.** `0` ok / `1` erreur d'utilisation / `2` échec d'authentification /
  `3` erreur serveur / `4` limite de débit / `5` introuvable. Les agents peuvent directement effectuer des branchements
  selon ces codes sans avoir à analyser les erreurs en langage naturel.
* **Aucune invite interactive en environnement headless.** Passez `--yes` (ou `-y`) aux
  commandes destructrices ; passez `--api-key` ou définissez `OMI_API_KEY` pour ignorer
  l'authentification interactive.
* **Comportement tolérant avec nouvelles tentatives.** Les erreurs `429` et `5xx` font l'objet d'une nouvelle tentative avec
  un délai d'attente exponentiel avant de propager l'erreur.

## Authentification (unique, par l'humain)

L'utilisateur obtient une clé d'API développeur depuis l'application web Omi
(`https://app.omi.me` → Developer → API Keys) et exécute l'une des deux options :

```bash
omi auth login                          # Collage interactif ; la clé ne s'inscrit pas dans l'historique du shell
# ou
export OMI_API_KEY=omi_dev_...          # Éphémère, adapté aux conteneurs
```

## Les cinq opérations les plus courantes des agents

### 1. Lire les souvenirs

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Créer un souvenir

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lire les conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lire les tâches en attente ouvertes

```bash
omi action-item list --json --open
```

### 5. Marquer une tâche en attente comme terminée

```bash
omi action-item complete --json a1b2c3d4
```

## API locale de Desktop

Lorsque Omi Desktop expose son API locale, les agents peuvent interroger l'historique
d'écran de l'appareil, les récapitulatifs, SQL et les tâches sans passer par l'API cloud de développement :

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou pour des sessions éphémères :
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

Ne terminez ou ne supprimez des tâches que lorsque l'utilisateur le demande explicitement :

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` enregistre la capture d'écran sur
le disque tout en continuant d'émettre du JSON sur stdout pour les scripts. L'ID de capture d'écran provient
généralement de `local search-screen` ou de requêtes SQL sur la table `screenshots`. Si Desktop
renvoie un échec structuré tel que `screenshot_pending`, `screenshot_file_missing`
ou `screenshot_chunk_corrupted`, le mode JSON conserve les champs `reason`, `hint`
et `screenshot_id` sur stderr afin que les agents puissent réessayer avec un ID plus ancien ou
signaler le problème précis. Validez les sorties réussies avec `file PATH` avant de les transmettre aux outils de vision.

## Exemple concret : boucle d'agent Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoque la CLI omi en mode JSON, levant une erreur en cas de code de sortie non nul."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # En mode JSON, la CLI renvoie des erreurs structurées sur stderr :
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lire toutes les tâches ouvertes et marquer comme terminées celles de plus de 30 jours.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestion des limites de débit

Souvenirs : 120/h. Conversations : 25/h. Créations groupées : 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite de débit atteinte
    err = json.loads(result.stderr)
    # err["detail"] ressemble à : "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Conseils pratiques

* Utilisez `--profile <nom>` si votre agent gère plusieurs comptes Omi. Chaque
  profil possède ses propres identifiants et son URL de base d'API.
* Utilisez `--api-base http://localhost:8080` pour les tests avec un backend local.
* Utilisez `OMI_LOCAL_API_URL` et `OMI_LOCAL_TOKEN` pour remplacer les paramètres
  de l'API Desktop du profil pour une seule exécution.
* Utilisez `--verbose` pour le débogage — consigne `METHOD path → status (Ns)` sur stderr
  sans affecter stdout, ce qui garantit la validité du mode JSON.
* Pour transmettre du contenu directement dans une conversation, utilisez `--text -` :
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
