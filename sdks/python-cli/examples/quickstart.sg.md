# Kua ti kôzo tî omi-cli

Fini mbëtï sô a fa kua ti kôzo (commands) tî omi-cli na Sängö. Irô tî kua ti kôzo na mbëtï tî programe a ga na Anglëe. Awâ kôzo tî gi (memories), tî tene (conversations), tî kua (action items) na tî mëngö (goals) tî mo a yeke nî ande.

## Zîa

Ti laâ: Python 3.10 wala kôzo kûê, na kônde Omi.

Sô mo yeke na `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mo lîngbi tî zîa nî na yâ tî virtual environment tî Python:

```sh
python -m pip install omi-cli
omi --help
```

Sô terminal a wara `omi` pëpe, bâa bîanî atâ virtual environment a yeke kua wala `pipx` folder a yeke na `$PATH`.

## Mû kônde tî mo

Tambûla na amû-kôde:

```sh
omi auth login
```

Soro tî lï na browser wala tî zîa API key tî Omi developer. Interaktif input a ndûu key sô; bâa tî sû nî na command tî terminal history.

Tî lï direktê na browser:

```sh
omi auth login --browser
```

Lï na komputere kûê na terminal: authentication mû-ndâ a lï na local address. Su ândikâ na screen.

Na pekô nî, bâa configuration na API access:

```sh
omi auth status
omi auth whoami
```

`status` a fa yâ tî local na a ndûu secret, me a bâa validité na server pëpe. `whoami` a mû request autentifié; sô a luti, a fa bîanî atâ credentials a yeke kua, na lâ tî fa irô tî mo.

Configuration a yeke na `~/.omi/config.toml`. Bâa tî ndûu mbëtï sô: a lîngbi tî yeke na credentials tî kôzo.

## Bâa données tî mo

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Liste tî sô a yeke vûa a fa pëpe tî gi. Hunda help tî wara filter tî kua kûê:

```sh
omi memory list --help
omi action-item list --help
```

## JSON na lâkûi

Zîa option tî yâ tî dunia `--json` **na kôzo** tî kua group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kua tî kôzo a hunda 25 memories tî kôzo; tî ûse a hunda 25 tî pekô. Lâkûi sô a yeke kôzo pëpe. JSON a bata nûméro kûê, me table na screen a lîngbi tî kpëngba nî.

Tî bata lâkûi na file:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

Zîa file tî local wala a sû na ndâ. Bâa bîanî kua a hunzi na kôzo tî mû yâ nî. Erreurs a yeke na error output (stderr); file tî vûa a fa pëpe atâ data a yeke. File sô a sara export a lîngbi tî yeke na information tî zo: bata nî na kôzo.

## Lï na pekô

```sh
omi auth logout
```

Kua sô a kpë credentials sô a bata na local. Tî zîa key na server, hunda developer key management na kônde tî mo.

Tî kua na option tî ndâ, bâa [mbëtï tî Anglëe](../README.md) na `omi --help`.
