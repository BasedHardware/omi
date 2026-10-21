# omi-cli pour les agents

> Guide pratique pour les environnements pilotés par LLM (Claude Code, Cursor, vos propres bots).

## Pourquoi le CLI est adapté aux agents

* **Contrat JSON stable.** `--json` émet un document JSON valide sur stdout et
  *uniquement* un document JSON — aucun message de progression, aucun indicateur de chargement. Les erreurs sont envoyées sur stderr sous la forme `{"error": "...", "detail": "..."}`.
* **Codes de sortie stables.** `0` succès / `1` erreur d'utilisation / `2` échec d'authentification / `3` erreur serveur / `4` limite de débit atteinte (rate limited) / `5` non trouvé. Les agents peuvent créer des branches conditionnelles sur ces codes sans analyser les erreurs en langage naturel.
* **Aucune invite interactive en contexte autonome (headless).** Passez `--yes` (ou `-y`) pour les commandes destructrices ; passez `--api-key` ou définissez `OMI_API_KEY` pour ignorer la connexion interactive.
* **Comportement de réessai tolérant.** Les erreurs `429` et `5xx` font l'objet de nouvelles tentatives avec interruption exponentielle (backoff) avant d'être remontées.

## Authentification (unique, effectuée par l'humain)

L'utilisateur obtient une clé d'API développeur depuis l'application web Omi
(`https://app.omi.me` → Developer → API Keys) et choisit l'une des options :

```bash
omi auth login                          # collage interactif ; la clé n'apparaît pas dans l'historique du shell
# ou
export OMI_API_KEY=omi_dev_...          # éphémère, adapté aux conteneurs
```

## Les cinq actions les plus fréquentes pour les agents

### 1. Lire les souvenirs (memories)

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

## API locale Desktop

Lorsque Omi Desktop expose son API locale, les agents peuvent interroger l'historique
d'écran sur l'appareil, les récapitulatifs, le SQL et les tâches sans utiliser l'API cloud développeur :

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou pour les sessions éphémères :
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

Terminez ou supprimez des tâches uniquement à la demande explicite de l'utilisateur :

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` écrit la capture d'écran sur
le disque tout en affichant du JSON sur stdout pour les scripts. L'ID de capture provient
généralement de `local search-screen` ou d'une requête SQL sur la table `screenshots`. Si Desktop
renvoie un échec structuré tel que `screenshot_pending`, `screenshot_file_missing`
ou `screenshot_chunk_corrupted`, le mode JSON conserve les champs `reason`, `hint` et
`screenshot_id` sur stderr afin que les agents puissent réessayer avec un ID plus ancien ou signaler le
point de blocage exact. Validez les sorties réussies avec `file PATH` avant de les transmettre
aux outils de vision.

## Exemple concret : boucle d'agent Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoque le CLI omi en mode JSON, levant une exception sur les codes de sortie non nuls."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Le CLI affiche des erreurs structurées sur stderr en mode JSON :
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lire tous les éléments d'action ouverts et marquer comme terminés ceux de plus de 30 jours.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestion des limites de débit (rate limits)

Souvenirs : 120/h. Conversations : 25/h. Créations par lots : 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite de débit atteinte
    err = json.loads(result.stderr)
    # err["detail"] ressemble à : "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Astuces

* Utilisez `--profile <nom>` si votre agent gère plusieurs comptes Omi. Chaque
  profil possède ses propres identifiants et son URL de base d'API.
* Utilisez `--api-base http://localhost:8080` pour les tests avec un backend local.
* Utilisez `OMI_LOCAL_API_URL` et `OMI_LOCAL_TOKEN` pour remplacer les paramètres
  de l'API Desktop du profil pour une seule exécution.
* Utilisez `--verbose` pour le débogage — cela consigne `METHOD path → status (Ns)` sur stderr
  sans affecter stdout, préservant ainsi la validité du flux JSON.
* Pour injecter du contenu dans une conversation via un tube (pipe), utilisez `--text -` :
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
