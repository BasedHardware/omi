# Guide de démarrage rapide omi-cli en français

> Guide pratique pour interagir avec Omi depuis votre terminal. Conçu pour les développeurs et les agents d'intelligence artificielle.

`omi-cli` est l'interface en ligne de commande officielle pour l'API développeur d'[Omi](https://omi.me). Elle permet d'interroger et de manipuler de façon scriptable les quatre ressources essentielles gérées par Omi : mémoires, conversations, tâches d'action et objectifs.

* **PyPI :** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentation officielle :** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Code source :** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

La méthode recommandée est d'utiliser `pipx`, qui isole les dépendances dans un environnement dédié :

```bash
# Recommandé : installation isolée avec pipx
pipx install omi-cli

# Ou via pip standard
pip install omi-cli
```

> **Important : Nom du paquet vs. Nom de commande**
> * Le nom du paquet Python sur PyPI est **`omi-cli`** (le nom `omi` seul appartient à un paquet non lié).
> * La commande à exécuter dans le terminal après l'installation est **`omi`**.

Vérifiez l'installation :

```bash
omi --version
omi --help
```

---

## 2. Authentification

`omi-cli` prend en charge deux méthodes d'authentification :

| Méthode | Cas d'usage principal | Exemple de commande |
| :--- | :--- | :--- |
| **Clé API Développeur (`omi_dev_*`)** | CI/CD, scripts d'automatisation, agents IA | `omi auth login --api-key ...` ou variable d'environnement |
| **OAuth via navigateur (Google / Apple)** | Développeurs sur machine locale | `omi auth login --browser` |

### Connexion interactive
Sans argument, un sélecteur interactif s'affiche :

```bash
omi auth login
# 1) Browser — Connexion via Google ou Apple dans le navigateur (pour humains)
# 2) API key — Coller une clé développeur depuis app.omi.me (pour agents/CI)
```

### Connexion directe via navigateur
```bash
omi auth login --browser
```

### Connexion avec une clé API
Obtenez votre clé sur [app.omi.me](https://app.omi.me) dans la section « Developer → API Keys » :

```bash
# Configuration par commande
omi auth login --api-key omi_dev_...

# Ou via variable d'environnement (idéal pour conteneurs ou CI)
export OMI_API_KEY=omi_dev_...
```

### Vérification de l'état de connexion
* `omi auth status` : Affiche le profil actif, les identifiants masqués et la date d'expiration (fonctionne hors ligne).
* `omi auth whoami` : Envoie une requête de test au serveur pour vérifier la validité des accès (nécessite une connexion réseau).

```bash
omi auth status
omi auth whoami
```

Pour vous déconnecter et purger les identifiants locaux :
```bash
omi auth logout
```

---

## 3. Utilisation de base

Manipulez les quatre ressources clés d'Omi :

### Mémoires (Memories)
Faits et apprentissages mémorisés par le système au sujet de l'utilisateur.

```bash
# Lister les mémoires
omi memory list

# Créer une nouvelle mémoire
omi memory create "L'utilisateur préfère le thème sombre" --category lifestyle

# Afficher les détails d'une mémoire
omi memory get <ID_MEMOIRE>
```

### Conversations (Conversations)
Échanges audio et textuels capturés par les appareils ou l'application.

```bash
# Afficher les 5 conversations les plus récentes
omi conversation list --limit 5

# Voir les détails et la transcription complète
omi conversation get <ID_CONVERSATION> --include-transcript
```

### Éléments d'action (Action Items)
Tâches et rappels extraits automatiquement des conversations.

```bash
# Lister uniquement les tâches en attente
omi action-item list --open

# Marquer une tâche comme terminée
omi action-item complete <ID_ACTION>
```

### Objectifs (Goals)
Indicateurs et objectifs dont vous suivez la progression.

```bash
# Lister les objectifs actifs
omi goal list
```

---

## 4. Automatisation et format JSON (`--json`)

`omi-cli` produit nativement du JSON pour faciliter l'intégration avec `jq` ou des scripts Python. Spécifiez `--json` comme **option globale avant le sous-verbe** :

```bash
# Obtenir la liste des mémoires au format JSON
omi --json memory list | jq '.[] | {id, content, category}'

# Récupérer les titres des conversations récentes
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Lister les tâches ouvertes en JSON
omi --json action-item list --open | jq '.'
```

> **Astuce :** Placez toujours `--json` **avant** la commande (`memory`, `conversation`, etc.) :
> * Correct : `omi --json memory list`
> * Incorrect : `omi memory list --json`

---

## 5. Codes de sortie (Exit Codes)

Pour faciliter les tests et scripts CI/CD :

| Code | Signification | Description |
| :---: | :--- | :--- |
| `0` | Succès (Success) | Commande exécutée avec succès |
| `1` | Erreur d'utilisation (Usage Error) | Argument ou option invalide |
| `2` | Erreur d'authentification (Auth Error) | Non connecté, clé invalide ou jeton expiré |
| `3` | Erreur serveur / réseau (Server Error) | Réponse 5xx, délai dépassé ou coupure réseau |
| `4` | Limite de débit atteinte (Rate Limited) | HTTP 429 Too Many Requests |
| `5` | Ressource introuvable (Not Found) | HTTP 404 (identifiant inexistant) |

---

## 6. Variables d'environnement selon le terminal

### Bash / Zsh (Linux / macOS)
```bash
# Définir la clé API
export OMI_API_KEY="omi_dev_votre_cle_ici"

# Exécuter en mode JSON
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# Définir la clé API
$env:OMI_API_KEY = "omi_dev_votre_cle_ici"

# Traiter le JSON sous PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. Intégration avec l'API Desktop Locale

Si l'application Omi Desktop tourne localement, vous pouvez interroger l'historique d'écran local ou la base SQL sans passer par le cloud :

```bash
# Configurer l'adresse et le jeton local
omi local configure --url http://127.0.0.1:47778 --token VOTRE_JETON_DESKTOP

# Vérifier le statut de l'API locale
omi --json local status

# Rechercher dans l'historique d'écran
omi --json local search-screen "facture" --days 7 --app Safari
```

---

## 8. Gestion des profils (Profiles)

Pour basculer entre plusieurs comptes (par exemple personnel et professionnel), utilisez l'option `--profile`. Les profils sont sauvegardés dans `~/.omi/config.toml` :

```bash
# Connexion avec un profil personnel
omi --profile personal auth login

# Connexion avec un profil professionnel
omi --profile work auth login

# Exécution sous le profil souhaité
omi --profile work memory list
```
