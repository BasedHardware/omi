# omi-cli pour les agents

> Guide pratique pour les environnements pilotés par LLM (Claude Code, Cursor, vos propres bots).

## Pourquoi le CLI est adapté aux agents

* **Contrat JSON stable.** `--json` émet un document JSON valide vers stdout et *uniquement* ce document — aucun message de progression ni spinner. Les erreurs sont écrites vers stderr sous la forme `{"error": "...", "detail": "..."}`.
* **Codes de sortie stables.** `0` ok / `1` erreur d'utilisation / `2` erreur de permission / `3` erreur serveur / `4` limite de débit / `5` non trouvé. Les agents peuvent se ramifier sur ces codes sans analyser le langage naturel dans les messages d'erreur.
* **Aucune invite interactive dans les contextes headless.** Passez `--yes` (ou `-y`) pour les commandes destructives ; passez `--api-key` ou définissez `OMI_API_KEY` pour ignorer la connexion interactive.
* **Logique de réessai indulgente.** Les codes `429` et `5xx` sont réessayés avec un backoff exponentiel avant d'être signalés.

## Authentification (une fois, par l'humain)

L'utilisateur récupère une clé API développeur depuis l'application web Omi (`https://app.omi.me` → Developer → API Keys) et exécute l'une des commandes suivantes :

```bash
omi auth login                          # collage interactif ; la clé ne va pas dans l'historique du shell
# oder / ou / ili / or / ή / veya / või / o / ale /
export OMI_API_KEY=omi_dev_...          # temporaire, compatible avec les conteneurs
```

## Les cinq choses que les agents font le plus

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

### 4. Lire les éléments d'action ouverts

```bash
omi action-item list --json --open
```

### 5. Marquer un élément d'action comme terminé

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop locale

Lorsque Omi Desktop expose son API locale, les agents peuvent interroger l'historique d'écran de l'appareil, les résumés, SQL et les tâches sans utiliser l'API dev cloud :

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# temporaire, compatible avec les conteneurs:
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

Terminez ou supprimez les tâches uniquement lorsque l'utilisateur le demande explicitement :

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` sauvegarde la capture d'écran sur le disque et écrit toujours du JSON vers stdout pour les scripts. Les ID de capture d'écran proviennent généralement de `local search-screen` ou de SQL sur la table `screenshots`. Si Desktop retourne une erreur structurée comme `screenshot_pending`, `screenshot_file_missing` ou `screenshot_chunk_corrupted`, le mode JSON préserve les champs `reason`, `hint` et `screenshot_id` vers stderr afin que les agents puissent réessayer avec un ID plus ancien ou signaler l'obstacle précis. Vérifiez les résultats réussis avec `file PATH` avant de les passer aux outils de vision.

## Exemple pratique : boucle d'agent Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Exécuter le CLI omi en mode JSON et lever une exception sur les mauvais codes de sortie."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Le CLI écrit des erreurs structurées vers stderr en mode JSON :
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi s'est terminé avec le code {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lire tous les éléments d'action ouverts et marquer ceux de plus de 30 jours comme terminés.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestion des limites de débit

Souvenirs : 120/heure. Conversations : 25/heure. Création par lot : 15/heure.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite de débit atteinte
    err = json.loads(result.stderr)
    # err["detail"] ressemble à : "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Conseils

* Utilisez `--profile <nom>` si votre agent gère plusieurs comptes Omi. Chaque profil a ses propres identifiants et sa propre base d'API.
* Utilisez `--api-base http://localhost:8080` pour les tests de backend local.
* Utilisez `OMI_LOCAL_API_URL` et `OMI_LOCAL_TOKEN` pour remplacer les paramètres d'API Desktop du profil pour une seule exécution.
* Utilisez `--verbose` pour le débogage — enregistre `METHOD path → status (Ns)` vers stderr sans affecter stdout, le mode JSON reste donc valide.
* Pour envoyer du contenu dans une conversation via pipe, utilisez `--text -` :
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
