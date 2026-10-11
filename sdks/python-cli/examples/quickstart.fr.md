# omi-cli — guide de démarrage rapide en français

> Guide pratique pour travailler avec Omi depuis le terminal. Convient aussi bien aux humains qu'aux agents IA.

`omi-cli` est le client en ligne de commande officiel de l'API développeur d'[Omi](https://omi.me).
Il donne un accès rapide et scriptable aux quatre entités principales d'Omi :
souvenirs, conversations, tâches et objectifs.

* **PyPI :** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentation :** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Code source :** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

La méthode recommandée est `pipx` : elle installe l'outil dans un environnement isolé,
afin que ses dépendances n'entrent pas en conflit avec vos projets.

```bash
# recommandé : installation via pipx
pipx install omi-cli

# ou via pip
pip install omi-cli
```

> **Important : le nom du paquet et le nom de la commande sont différents.**
> * Le paquet installé est **`omi-cli`** (le paquet distinct `omi` est un autre projet, sans rapport).
> * Après l'installation, vous exécutez la commande **`omi`**.

Vérifiez que tout fonctionne :

```bash
omi --version
omi --help
```

---

## 2. Authentification

`omi-cli` prend en charge deux façons de se connecter.

| Méthode | Adaptée à | Commande |
| :--- | :--- | :--- |
| **Clé développeur (`omi_dev_*`)** | CI/CD, scripts, agents IA | `omi auth login --api-key ...` ou variable d'environnement |
| **Connexion navigateur (Google/Apple)** | Travail sur sa propre machine | `omi auth login --browser` |

### Connexion interactive

Sans option, la commande demande elle-même quelle méthode utiliser :

```bash
omi auth login
# 1) Browser — connexion avec Google ou Apple (pratique pour les humains)
# 2) API key — coller la clé développeur depuis app.omi.me (pratique pour les agents et la CI)
```

Si vous choisissez la clé, la saisie est masquée afin que la clé ne reste pas dans l'historique du terminal.

### Directement via le navigateur

```bash
omi auth login --browser
```

### Via une clé développeur

La clé se récupère sur [app.omi.me](https://app.omi.me) sous **Developer → API Keys**.

```bash
# enregistrer la clé dans la configuration
omi auth login --api-key omi_dev_...

# ou la passer via l'environnement — à privilégier pour CI/CD et les conteneurs
export OMI_API_KEY=omi_dev_...
```

La variable d'environnement `OMI_API_KEY` est utilisée quand aucune clé n'est enregistrée
dans le profil actif ; dans un conteneur, rien n'a donc besoin d'être écrit sur le disque.
Si le profil possède déjà une clé, celle-ci a la priorité sur la variable d'environnement.

### Vérifier la connexion

Deux commandes répondent à des questions différentes et ne doivent pas être confondues :

* `omi auth status` — ce qui est enregistré **en local** : profil, clé masquée, date d'expiration.
  Fonctionne sans réseau.
* `omi auth whoami` — requête **vers le serveur Omi** : vérifie que la clé est réellement
  acceptée. Nécessite le réseau.

```bash
omi auth status    # vérification locale, hors ligne
omi auth whoami    # vérification côté serveur
```

Renouveler un token sur le point d'expirer sans se reconnecter — cette commande ne s'applique
**qu'aux sessions navigateur/OAuth**. Pour un profil authentifié par clé API (`omi_dev_*`),
`omi auth refresh` échoue avec une erreur d'usage (code 1) : il n'y a pas de token à renouveler —
faites pivoter la clé depuis l'application web Omi si nécessaire :

```bash
omi auth refresh
```

Se déconnecter :

```bash
omi auth logout
```

---

## 3. Commandes de base

### Souvenirs (memories)

Faits et connaissances que le système a retenus à votre sujet.

```bash
# liste des souvenirs
omi memory list

# en créer un nouveau
omi memory create "L'utilisateur préfère le thème sombre" --category lifestyle

# en consulter un en particulier
omi memory get <MEMORY_ID>
```

### Conversations

Historique vocal et textuel provenant de l'appareil ou de l'application.

```bash
# les 5 conversations les plus récentes
omi conversation list --limit 5

# une conversation complète avec sa transcription
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Tâches (action items)

Tâches qu'Omi a déduites des conversations.

```bash
# uniquement les tâches ouvertes
omi action-item list --open

# marquer comme terminée
omi action-item complete <ACTION_ITEM_ID>
```

### Objectifs (goals)

```bash
# liste des objectifs
omi goal list

# enregistrer une nouvelle valeur de progression (requiert LES DEUX arguments : objectif et valeur)
omi goal progress <GOAL_ID> 25

# historique des modifications
omi goal history <GOAL_ID>
```

---

## Poser des questions dans vos propres mots (`ask`)

Une commande de premier niveau distincte : pose une question en langage naturel,
et la réponse est construite à partir de vos propres conversations.

```bash
omi ask "qu'est-ce que j'ai décidé à propos du déménagement"
omi --json ask "quelles tâches ai-je promis de clôturer cette semaine"
```

---

## 4. JSON et scripts (`--json`)

`omi-cli` peut produire du JSON lisible par machine. L'option `--json` est **globale**
et se place donc **avant** la sous-commande.

```bash
# souvenirs : extraire id, texte et catégorie
omi --json memory list | jq '.[] | {id, content, category}'

# titres des conversations récentes
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# tâches ouvertes
omi --json action-item list --open | jq '.'
```

> **Erreur fréquente.** `--json` vient avant la sous-commande, pas après.
> * Correct : `omi --json memory list`
> * Incorrect : `omi memory list --json`

En mode `--json`, rien d'autre que le JSON lui-même n'est écrit sur stdout —
les scripts peuvent s'y fier.

---

## 5. Codes de sortie

Les codes sont stables : la logique des scripts et de la CI peut s'y brancher.

| Code | Signification | Quand |
| :---: | :--- | :--- |
| `0` | Succès | La commande s'est exécutée |
| `1` | Erreur d'appel | Validation propre à omi-cli (p. ex. `--browser` et `--api-key` à la fois, choix de connexion invalide, stdin vide) |
| `2` | Erreur d'accès | Non connecté, clé invalide ou expirée |
| `3` | Erreur serveur | Réponse 5xx, délai dépassé, pas de connexion |
| `4` | Trop de requêtes | 429 Too Many Requests |
| `5` | Introuvable | 404, l'identifiant n'existe pas |

> **Remarque.** Les options inconnues et les arguments manquants sont interceptés par Click et donnent le code `2`.

Exemple de vérification en Bash :

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "la clé fonctionne"
else
  code=$?
  [ "$code" -eq 2 ] && echo "reconnectez-vous"
  [ "$code" -eq 3 ] && echo "le serveur est en panne, réessayez plus tard"
fi
```

---

## 6. Variables d'environnement

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_votre_clé"

omi --json memory list --limit 10
```

Pour que la clé soit chargée dans les nouvelles sessions, ajoutez la ligne à `~/.bashrc` ou `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_votre_clé"

# parsing JSON avec PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Pour une configuration permanente :

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_votre_clé", "User")
```

---

## 7. L'application Omi Desktop en local

Si l'application de bureau Omi est en cours d'exécution, une partie des données est
accessible directement, sans passer par le cloud.

```bash
# indiquer l'adresse de l'API locale
omi local configure --url http://127.0.0.1:47778 --token VOTRE_TOKEN

# vérifier qu'elle répond
omi --json local status

# recherche dans l'historique d'écran
omi --json local search-screen "tarifs" --days 7 --app Safari

# capture d'écran par identifiant
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# SQL arbitraire contre la base locale
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Déroulement conseillé : d'abord `local status`, puis `local tools` — pour voir les outils
disponibles et leurs paramètres — et seulement ensuite les appels.

---

## 8. Profils

Si vous avez plusieurs comptes ou environnements, séparez-les avec des profils.
Les paramètres sont enregistrés dans `~/.omi/config.toml`.

```bash
# connexion au profil personnel
omi --profile personal auth login

# connexion au profil professionnel
omi --profile work auth login

# exécuter une commande dans un profil donné
omi --profile work memory list
```

Le profil utilisé est déterminé dans cet ordre : l'option `--profile` (ou `-p`) l'emporte
sur tout le reste ; sinon la variable d'environnement `OMI_PROFILE` ; sinon le profil actif
défini dans `~/.omi/config.toml` ; et en dernier recours le profil `default`.

Voir et modifier la configuration elle-même :

```bash
# ce qui est configuré actuellement
omi config show

# où se trouve le fichier de configuration
omi config path

# modifier une valeur
omi config set api_base https://api.omi.me
```

---

## 9. Prochaines étapes

* [`agent_quickstart.md`](./agent_quickstart.md) — comment connecter `omi-cli` à un agent IA.
* [`shell_examples.sh`](./shell_examples.sh) — exemples prêts à l'emploi pour le shell.
* [Documentation Omi](https://docs.omi.me/doc/developer/cli/introduction) — la référence complète des commandes.
