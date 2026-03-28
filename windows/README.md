## Omi Windows – Guide contributeur

### 1. Objectif

Ce dossier contient une première implémentation d’un client Windows natif (WPF) pour Omi, qui se branche sur les **endpoints publics existants** :

- Backend principal : `https://api.omi.me`
- Authentification : `/v1/auth/authorize`, `/v1/auth/callback/*`, `/v1/auth/token`
- WebSocket STT temps réel : `/v4/listen`

L’app Windows suit le même modèle que les autres clients : tout passe par **Firebase Auth** (ID token), vérifié côté serveur.

---

### 2. Pré-requis

- Windows 11
- .NET 9 SDK (`dotnet --version` ≈ 9.x)

Variables d’environnement recommandées :

- `OMI_API_BASE_URL` (optionnel) : URL de base de l’API, défaut : `https://api.omi.me/`.
- `OMI_FIREBASE_API_KEY` **ou** `FIREBASE_API_KEY` : clé Web Firebase utilisée par le frontend Omi (publique, pas un secret serveur).

---

### 3. Lancer l’app Windows en local

Dans la racine du mono-repo :

```powershell
cd D:\omi
dotnet run --project windows/App/Omi.Windows.App.csproj
```

Une fenêtre “Connexion Omi” apparaît au premier lancement.

---

### 4. Flux d’authentification (Apple/Google)

L’app ne gère **pas** directement le flux OAuth : elle délègue entièrement au backend Python existant (`backend/routers/auth.py`).

#### Étapes côté utilisateur (mode manuel actuel)

1. Dans la fenêtre “Connexion Omi”, clique sur **“Ouvrir la page de connexion”**.  
   Cela ouvre dans ton navigateur :

   ```text
   https://api.omi.me/v1/auth/authorize?provider=apple&redirect_uri=omi://auth/callback
   ```

2. Connecte‑toi avec Apple (ou Google une fois supporté côté UI), comme tu le fais déjà dans les autres apps Omi.

3. À la fin, tu es redirigé vers une URL de callback du type :

   ```text
   omi://auth/callback?code=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

   Copie **la valeur du paramètre `code`**.

4. Colle ce `code` dans la zone de texte de la fenêtre “Connexion Omi”, puis clique sur **“Valider”**.

#### Ce qui se passe côté app Windows

La méthode `AuthService.SignInWithAuthCodeAsync` :

1. Appelle `POST /v1/auth/token` sur l’API Omi existante :

   - Body `x-www-form-urlencoded` :

     - `grant_type=authorization_code`
     - `code=<code_collé>`
     - `redirect_uri=omi://auth/callback`
     - `use_custom_token=true`

   - Le backend retourne :

     - `provider` (apple/google),
     - `id_token` + `access_token` du provider,
     - `provider_id`,
     - `custom_token` (Firebase custom token) si `use_custom_token=true`.

2. Échange `custom_token` contre un **Firebase ID token** via l’API publique Firebase Identity Toolkit :

   ```text
   POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=<FIREBASE_API_KEY>
   {
     "token": "<custom_token>",
     "returnSecureToken": true
   }
   ```

   → Réponse : `idToken`, `refreshToken`, `localId`, etc.

3. Stocke `idToken` en local (registre Windows, clé `HKCU\Software\Omi\WindowsApp\IdToken`) et l’utilise comme **token d’authentification** pour :

   - les requêtes HTTP sécurisées (via `HttpApiClient`),
   - le WebSocket `/v4/listen` (via `SttWebSocketClient`).

Le backend `/v4/listen` voit donc un **Firebase ID token** standard et le valide exactement comme pour les clients mobile/macOS.

---

### 5. Tester la capture audio + STT

Une fois connecté (fenêtre de login fermée) :

1. Clique sur **“Démarrer l’enregistrement”**.
2. Parle quelques secondes dans ton micro.
3. Clique sur **“Arrêter”**.
4. Observe la grande zone de texte :
   - en cas de succès, tu verras les messages JSON renvoyés par `/v4/listen` (segments, events, etc.),
   - en cas d’erreur (ex. token invalide, 403), tu verras un JSON d’erreur explicite sans que l’app ne se ferme.

---

### 6. Notes pour contributions futures

- **Schéma de callback** : pour une meilleure UX, on pourra enregistrer un schéma `omi://auth/callback-windows` via l’installer Windows, pour éviter le copier/coller manuel du `code`.
- **Provider Google** : le flux `/v1/auth/authorize?provider=google` est déjà supporté côté backend ; il suffira d’ajouter une option dans l’UI Windows pour le sélectionner.
- **Sécurité** : la clé `FIREBASE_API_KEY` est une clé web publique (comme sur les autres clients). Les secrets sensibles (service account, etc.) restent sur le backend Python/Firebase Admin, jamais embarqués dans l’app Windows.

