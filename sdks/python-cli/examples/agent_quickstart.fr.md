# omi-cli pour les agents

> Guide pratique pour les harnais pilotés par LLM (Claude Code, Cursor, vos propres bots).

## Pourquoi la CLI convient aux agents

* **Contrat JSON stable.** `--json` écrit sur stdout un document JSON valide et
  *uniquement* un document JSON — pas de messages de progression, pas de spinners.
  Les erreurs partent sur stderr sous la forme `{"error": "...", "detail": "..."}`.
* **Codes de sortie stables.** `0` ok / `1` erreur d'usage / `2` authentification /
  `3` serveur / `4` limite de débit / `5` introuvable. Les agents peuvent brancher
  leur logique dessus sans analyser des messages en langage naturel.
* **Aucune invite interactive en contexte headless.** Passez `--yes` (ou `-y`) aux
  commandes destructrices ; passez `--api-key` ou définissez `OMI_API_KEY` pour
  éviter la connexion interactive.
* **Réessais tolérants.** Les `429` et `5xx` sont réessayés avec backoff avant
  d'être remontés.

## Authentification (une seule fois, par l'humain)

L'utilisateur récupère une clé développeur dans l'application web Omi
(`https://app.omi.me` → Developer → API Keys), puis fait l'une des deux choses
suivantes :

```bash
omi auth login                          # collage interactif ; la clé ne reste pas dans l'historique du shell
# ou
export OMI_API_KEY=omi_dev_...          # éphémère, adapté aux conteneurs
```

## Les cinq opérations les plus courantes pour un agent

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

### 4. Lire les tâches ouvertes

```bash
omi action-item list --json --open
```

### 5. Marquer une tâche comme terminée

```bash
omi action-item complete --json a1b2c3d4
```

## API locale de Desktop

Lorsque Omi Desktop expose son API locale, les agents peuvent interroger
l'historique d'écran, les récapitulatifs, le SQL et les tâches présents sur la
machine sans passer par l'API développeur dans le cloud :

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou, pour des sessions éphémères :
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

Ne terminez ou ne supprimez des tâches que si l'utilisateur le demande
clairement :

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` écrit la capture d'écran sur
le disque tout en continuant d'imprimer du JSON sur stdout pour les scripts.
L'identifiant de la capture provient en général de `local search-screen` ou d'une
requête SQL sur la table `screenshots`. Si Desktop renvoie un échec structuré tel
que `screenshot_pending`, `screenshot_file_missing` ou
`screenshot_chunk_corrupted`, le mode JSON conserve les champs `reason`, `hint`
et `screenshot_id` sur stderr, de sorte que l'agent peut réessayer avec un
identifiant plus ancien ou signaler le blocage exact. Validez les sorties
réussies avec `file PATH` avant de les transmettre à des outils de vision.

## Exemple complet : boucle d'agent en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Appelle la CLI omi en mode JSON et lève une exception si le code de sortie n'est pas 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # En mode JSON, la CLI écrit des erreurs structurées sur stderr :
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lire toutes les tâches ouvertes et terminer celles de plus de 30 jours.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gérer les limites de débit

Souvenirs : 120/h. Conversations : 25/h. Créations par lot : 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite de débit
    err = json.loads(result.stderr)
    # err["detail"] ressemble à : "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Conseils

* Utilisez `--profile <name>` si votre agent jongle avec plusieurs comptes Omi.
  Chaque profil a ses propres identifiants et son propre API base.
* Utilisez `--api-base http://localhost:8080` pour tester un backend local.
* Utilisez `OMI_LOCAL_API_URL` et `OMI_LOCAL_TOKEN` pour remplacer, le temps
  d'une exécution, les réglages de l'API Desktop enregistrés dans le profil.
* Utilisez `--verbose` pour déboguer : il journalise `METHOD path → status (Ns)`
  sur stderr sans toucher à stdout, donc le mode JSON reste valide.
* Pour envoyer du contenu dans une conversation via un tube, utilisez `--text -` :
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
