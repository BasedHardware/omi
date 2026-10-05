# omi-cli (Français)

[English README](README.md) · [Русский: быстрый старт](README.ru.md) · [日本語 README](README.ja.md) · [Guide de démarrage rapide en français](examples/quickstart.fr.md)

> Interagissez avec Omi depuis votre terminal. Conçu pour les humains **et** les agents.

`omi-cli` est l'interface en ligne de commande pour l'API développeur d'[Omi](https://omi.me). Elle expose des verbes ciblés et adaptés aux agents pour les quatre concepts fondamentaux qu'Omi conserve à votre sujet:

* **mémoires:** faits et apprentissages que le système connaît sur vous
* **conversations:** échanges audio et textuels capturés et traités
* **éléments d'action:** tâches et suivis
* **objectifs:** indicateurs de progression suivis

Conçu intentionnellement pour être compact, scriptable et axé sur le JSON: tout ce dont vous avez besoin pour intégrer Omi dans vos pipelines shell, vos jobs CI, vos environnements d'agents ou vos automatisations personnelles.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Code source:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

## Installation

```bash
pipx install omi-cli            # recommandé: installation isolée
# ou
pip install omi-cli
```

Après installation, le binaire disponible dans votre `$PATH` se nomme `omi`:

```bash
omi --version
omi --help
```

> Le nom de distribution sur PyPI est `omi-cli` (l'identifiant `omi` étant attribué à un paquet distinct). La commande en console reste `omi` dans tous les cas.

## Démarrage rapide

```bash
# 1. Connexion. Sans option, omi-cli vous demande comment vous souhaitez vous authentifier:
omi auth login
# -> 1) Browser: connexion avec Google ou Apple (recommandé pour les humains)
# -> 2) API key: coller une clé développeur issue de app.omi.me (recommandé pour les agents/CI)

# 2. Premiers pas:
omi memory list
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ajoutez `--json` à n'importe quelle commande (comme option globale, avant le verbe) pour obtenir une sortie exploitable par machine, compatible avec `jq`, vos pipelines d'agents ou tout autre outil:

```bash
omi --json memory list | jq '.[] | {id, content}'
```

L'affichage standard affiche le texte retourné tel quel, y compris les crochets et les codes de style emoji comme `:warning:`. Le style s'applique à la disposition du tableau, et non au contenu de vos mémoires ou conversations.
Les tableaux sans colonnes prédéfinies incluent les champs de chaque ligne selon leur ordre de première apparition.

> Pour consulter les guides dans d'autres langues, reportez-vous à [`examples/README.md`](examples/README.md). Le guide de démarrage rapide en français est accessible sur [`examples/quickstart.fr.md`](examples/quickstart.fr.md).

## Authentification

Deux méthodes d'authentification, toutes deux entièrement prises en charge:

| Méthode | Idéale pour | Utilisation |
| --- | --- | --- |
| Clé API développeur (`omi_dev_*`) | Agents, CI, headless, autorisations ciblées | `omi auth login --api-key ...` ou variable d'environnement |
| Firebase OAuth (Google/Apple) | Humains sur ordinateur portable | `omi auth login --browser` |

Le flux par navigateur ouvre votre navigateur par défaut pour OAuth, capture le code via un rappel sur localhost et enregistre un jeton d'ID Firebase ainsi qu'un jeton d'actualisation. Le jeton d'ID est automatiquement renouvelé avant chaque requête lorsqu'il approche de son expiration: vous n'avez pas à vous en préoccuper.

```bash
omi auth login                  # sélecteur interactif (navigateur ou clé)
omi auth login --browser        # forcer OAuth (fournisseur par défaut: google)
omi auth login --browser --provider apple
omi auth login --api-key K      # forcer le mode clé API
omi auth login < key.txt        # clé transmise par tube, pratique en CI
omi auth status                 # affiche le profil, les identifiants masqués et l'expiration
omi auth whoami                 # interrogation du serveur pour vérifier la validité
omi auth refresh                # forcer l'actualisation Firebase (sans effet pour les clés API)
omi auth logout                 # supprimer les identifiants
```

Une clé API est vérifiée avant d'écraser les identifiants enregistrés. Si la vérification est rejetée avec une erreur HTTP 401 ou 403, le profil existant et la sélection du profil actif restent inchangés. Les autres erreurs HTTP conservent le comportement habituel d'enregistrement avec avertissement. Une défaillance réseau préserve les identifiants sauvegardés; l'authentification OAuth par navigateur constitue un flux distinct.

Vous pouvez également définir une variable d'environnement `OMI_API_KEY` non vide pour remplacer l'authentification enregistrée lors des requêtes d'API cloud: très pratique en conteneur ou en CI. La clé est validée même si le profil sélectionné contient déjà des identifiants; une valeur invalide échoue avant toute requête vers le cloud. Les commandes locales pour Desktop utilisent leur propre jeton local, et `auth status` rapporte le profil enregistré. Les identifiants enregistrés ne sont pas modifiés, et les paramètres de profil tels que l'URL de base de l'API restent appliqués:

```bash
export OMI_API_KEY=omi_dev_...
omi memory list
```

## Profils

La configuration réside dans `~/.omi/config.toml` (remplaçable via `$OMI_CONFIG`). Le fichier contient un ou plusieurs profils nommés, chacun doté de sa propre méthode d'authentification et de son URL de base d'API. L'enregistrement de la configuration préserve les paramètres inconnus tant au niveau racine qu'au niveau des profils, de sorte que la modification d'un paramètre connu ne supprime pas les extensions ajoutées par des clients plus récents. Basculez d'un profil à l'autre avec `--profile`:

```bash
omi config profile use work
omi auth login                  # connecte le profil actif (work)
omi --profile personal memory list
```

Commandes de configuration courantes:

```bash
omi config show
omi config path
omi config set api_base https://api.staging.omi.me
omi config set local_api_url http://127.0.0.1:47778
omi config set local_token ...
omi config profile list
omi config profile delete old-account --yes
```

## API locale Omi Desktop

`omi local` communique avec l'API locale d'une instance active d'Omi Desktop. Configurez le profil actif une seule fois ou utilisez des variables d'environnement pour des sessions d'agents temporaires:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...
```

Outils locaux courants:

```bash
omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local recap --days-ago 1
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
omi --json local task search "taxes" --include-completed
```

Flux de travail pour agents sur l'historique d'écran:

1. Vérifiez la disponibilité avec `omi --json local status`; examinez `screen_history_available`, `screenshot_count` et `indexed_screenshot_count`.
2. Consultez le schéma des outils via `omi --json local tools`.
3. Recherchez dans l'historique OCR/écran avec `omi --json local search-screen "query" --days 7` ou exécutez du SQL direct sur `screenshots` si des filtres d'application ou de fenêtre sont requis.
4. Utilisez le `screenshot_id` obtenu avec `omi --json local screenshot <id> --output /tmp/omi-shot.jpg`.
5. Validez le fichier avant de le transmettre aux outils de vision, par exemple avec `file /tmp/omi-shot.jpg`.

Si la recherche sémantique ne renvoie aucun résultat, le mode JSON effectue également une recherche littérale par sous-chaîne sur les noms d'applications, les titres de fenêtres et le texte OCR. Dans ce repli, les caractères `%` et `_` dans la requête ou dans le filtre `--app` correspondent littéralement à ces caractères au lieu d'agir comme des jokers SQL.

Si l'image n'est pas disponible, les erreurs en mode JSON conservent les champs structurés de Desktop tels que `status_code`, `error`, `reason`, `hint` et `screenshot_id`. Par exemple, `screenshot_pending` signifie que l'image est encore dans le segment vidéo actif; réessayez peu après ou choisissez un identifiant de capture plus ancien dans les résultats de recherche.

Les commandes modifiant les tâches ne doivent être exécutées que lorsque l'utilisateur a expressément demandé cette modification:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

### Appliquer la période demandée à la recherche exacte sur écran

Le repli exact par application, fenêtre et OCR pour `omi --json local search-screen` respecte la même période glissante `--days` que la recherche sémantique.

## Arborescence des commandes

L'arbre complet (exécutez `omi --help` pour voir l'arbre de commandes de la version installée):

```text
omi
├── auth
│   ├── login [--browser] [--api-key KEY]
│   ├── logout
│   ├── status
│   ├── whoami
│   └── refresh
├── config
│   ├── show
│   ├── path
│   ├── set <key> <value>
│   └── profile
│       ├── list
│       ├── use <name>
│       └── delete <name>
├── memory
│   ├── list [--limit N] [--offset N] [--categories ...]
│   ├── get <id>
│   ├── create <content> [--category ...] [--visibility ...] [--tag ...]
│   ├── update <id> [--content ...] [--category ...] [--visibility ...] [--tag ...]
│   └── delete <id> [-y]
├── conversation
│   ├── list [--limit N] [--start-date ...] [--end-date ...] [--include-transcript]
│   ├── get <id> [--include-transcript]
│   ├── create [--text ...] [--text-source ...] [...]
│   ├── from-segments <file.json> [--source ...]
│   ├── update <id> [--title ...] [--discarded/--no-discarded]
│   └── delete <id> [-y]
├── action-item
│   ├── list [--completed/--open] [--conversation-id ...] [...]
│   ├── get <id>
│   ├── create <description> [--due-at ...]
│   ├── update <id> [--description ...] [--completed/--open] [--due-at ...]
│   ├── complete <id>
│   └── delete <id> [-y]
├── local
│   ├── configure --url URL --token TOKEN
│   ├── status
│   ├── tools
│   ├── call <tool> [--args-json JSON]
│   ├── search-screen <query> [--days N] [--app NAME]
│   ├── screenshot <id> [--output PATH]
│   ├── recap [--days-ago N]
│   ├── sql <query>
│   └── task
│       ├── search <query> [--include-completed]
│       ├── complete <id>
│       └── delete <id> [-y]
└── goal
    ├── list [--limit N] [--include-inactive]
    ├── get <id>
    ├── create <title> --target N [--type ...] [--current N] [--unit ...]
    ├── update <id> [--unit ... | --clear-unit] [...]
    ├── progress <id> <value>
    ├── history <id> [--days N]
    └── delete <id> [-y]
```

`conversation from-segments` lit les fichiers JSON au format UTF-8 (avec ou sans BOM), UTF-16 ou UTF-32, indépendamment de l'encodage par défaut du système.
Le JSON de transcription tout comme `local call --args-json` exigent des nombres finis: `NaN`, `Infinity`, `-Infinity` ainsi que les valeurs hors de portée des nombres à virgule flottante de Python sont rejetés avant l'ouverture du client API. En mode `--json`, ces erreurs de saisie sont signalées sous forme de JSON sur stderr.

Les options numériques et les valeurs de progression des objectifs doivent également être finies. `NaN`, les valeurs infinies et les exposants en dépassement de capacité sont rejetés avant toute requête API.

`action-item get` parcourt successivement les pages de l'API jusqu'à trouver l'identifiant ou atteindre la fin des résultats. La commande peut récupérer des éléments au-delà des 1 000 premiers; la recherche d'un élément ancien ou inexistant peut nécessiter plusieurs requêtes API.

## Options globales

```text
--json                 Émet du JSON sur stdout (lisible par machine, adapté aux agents).
--profile, -p NAME     Utilise un profil spécifique.
--api-base URL         Remplace l'URL de base de l'API.
--verbose, -v          Enregistre le trafic HTTP sur stderr.
--no-color             Désactive la sortie colorée (respecte également $NO_COLOR).
--version              Affiche la version installée.
--help                 Affiche l'aide contextuelle.
```

## Codes de sortie (contrat stable)

```text
0  succès
1  erreur d'utilisation (options invalides, arguments manquants, validation)
2  erreur d'authentification (aucun identifiant, jeton expiré, permissions insuffisantes)
3  erreur serveur (5xx, échec de connexion)
4  limite de débit atteinte (429): nouvelle tentative recommandée
5  non trouvé (404)
```

## Pour les agents

Le CLI est conçu pour qu'un LLM puisse l'utiliser sans surcouche:

* `--json` renvoie du JSON valide sur stdout. Rien d'autre n'est écrit sur stdout en mode JSON (les erreurs vont sur stderr sous la forme `{"error": "...", "detail": "..."}`).
* Utilisez `omi --json version` pour obtenir un objet de version lisible par machine (`{"version": "..."}`). `omi version` et l'option directe `omi --version` conservent leur sortie en texte brut.
* Les codes de sortie stables (ci-dessus) permettent à un agent de distinguer les erreurs réessayables des erreurs terminales.
* Les commandes de suppression `delete --yes` réussies préservent la réponse de l'API en mode JSON. Une réponse positive sans corps est émise sous la forme de `null` en JSON.
* Les erreurs de limitation de débit incluent un délai `Retry-After` dans le message et indiquent le nom de la politique (`dev:conversations`, etc.) afin que l'agent puisse temporiser intelligemment.
* Les variables d'environnement `OMI_API_KEY` et `OMI_API_BASE` fonctionnent sans nécessiter d'exécution préalable de `auth login`.
* `OMI_LOCAL_API_URL` et `OMI_LOCAL_TOKEN` remplacent les paramètres d'API Desktop du profil pour `omi local`.

Consultez [`examples/agent_quickstart.fr.md`](examples/agent_quickstart.fr.md) (version en anglais: [`examples/agent_quickstart.md`](examples/agent_quickstart.md)) pour un exemple complet.

## Limites de débit

L'API développeur applique des quotas horaires par politique:

| Politique | Limite |
| --- | --- |
| `dev:conversations` | 25/heure |
| `dev:memories` | 120/heure |
| `dev:memories_batch` | 15/heure |

Le CLI réessaie automatiquement les requêtes `429` avec un intervalle exponentiel et respecte l'indication `Retry-After` du serveur lorsqu'elle est fournie. Lorsque toutes les tentatives sont épuisées, vous obtenez le code de sortie `4` accompagné d'un message précisant la durée d'attente.

Les requêtes POST et PATCH ne sont pas rejouées automatiquement après une défaillance réseau ambiguë ou une erreur serveur: le serveur a potentiellement déjà appliqué la modification. Ces défaillances renvoient le code de sortie `3` avec le message `outcome unknown`. Vérifiez l'état de la ressource avant de réitérer. Les échecs d'établissement de connexion et les réponses de limitation de débit continuent d'être retentés; les réessais en lecture demeurent inchangés.

## Autoriser la suppression de l'échéance d'un élément d'action

`omi action-item update ID --clear-due-at` supprime l'échéance sur les serveurs prenant en charge les champs PATCH nuls explicites (correctif backend #13029). Cette option ne peut être combinée avec `--due-at`. Omettre les deux conserve l'échéance inchangée.

## Préserver la sortie ambiguë des tableaux SQL

`omi --json local sql` conserve les tableaux d'affichage ambigus ou tronqués sous forme de texte brut dans le champ `text` plutôt que d'ignorer silencieusement des cellules. Les réponses Desktop structurées sont transmises sans altération; l'affichage textuel ne constitue pas un protocole de transport SQL sans perte.

## Options de date et heure

Les options de date et heure pour les conversations et les éléments d'action acceptent les horodatages ISO avec `Z` (UTC), les décalages numériques et les fractions de seconde facultatives, par exemple `--due-at 2026-09-08T12:30:00Z` ou `--start-date 2026-09-08T12:30:00.123456+05:30`. Les décalages sont préservés dans les requêtes API. Les valeurs composées uniquement d'une date et les horodatages sans décalage restent pris en charge; le CLI n'attribue pas de fuseau horaire à ces saisies.

## Développement

```bash
# Installation modifiable avec les dépendances de développement
pip install -e .[dev]

# Exécuter la suite de tests
pytest -q

# Lint
black --check --line-length 120 --skip-string-normalization sdks/python-cli/
mypy omi_cli

# Construire le wheel et la distribution source (sans publication ni tag)
bash release.sh --build-only
```

## Licence

MIT: voir [`LICENSE`](LICENSE).
