# První kroky s omi-cli

Tato příručka vysvětluje základní příkazy v češtině. Názvy příkazů a zprávy
programu zůstávají v angličtině. Zde uvedené příklady dotazů nemění vaše vzpomínky,
konverzace, úkoly ani cíle.

## Instalace programu

Požadavky: Python 3.10 nebo novější a účet Omi.

Pokud máte nainstalovaný `pipx`:

```sh
pipx install omi-cli
omi --help
```

Případně jej můžete nainstalovat v aktivovaném virtuálním prostředí Pythonu:

```sh
python -m pip install omi-cli
omi --help
```

Pokud terminál nenajde `omi`, zkontrolujte, zda je virtuální prostředí aktivováno
nebo zda je adresář, kam `pipx` instaluje spustitelné soubory, ve vaší proměnné `PATH`.

## Připojení vašeho účtu

Spusťte interaktivního průvodce:

```sh
omi auth login
```

Zvolte přihlášení přes prohlížeč nebo možnost vložit vývojářský API klíč Omi.
Interaktivní vstup klíč skryje; nepište jej do příkazu, který by zůstal v historii terminálu.

Pro přímé otevření prohlížeče:

```sh
omi auth login --browser
```

Přihlaste se na stejném počítači, kde běží terminál: autentizační odpověď používá
místní adresu. Postupujte podle pokynů na obrazovce.

Poté ověřte konfiguraci a přístup k API:

```sh
omi auth status
omi auth whoami
```

`status` zobrazuje místní stav a skrývá tajemství, ale neověřuje platnost na serveru.
`whoami` odešle ověřený požadavek; v případě úspěchu potvrdí funkčnost přihlašovacích údajů bez nutnosti zobrazovat vaše jméno.

Konfigurace se standardně ukládá do `~/.omi/config.toml`. Tento soubor nesdílejte:
může obsahovat vaše důvěrné přihlašovací údaje.

## Prohlížení vašich dat

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prázdný seznam může jednoduše znamenat, že dotazu neodpovídají žádné položky.
Pomocí nápovědy zjistíte filtry pro každý příkaz:

```sh
omi memory list --help
omi action-item list --help
```

## Získání JSON a stránkování

Umístěte globální volbu `--json` **před** skupinu příkazů:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

První příkaz si vyžádá prvních 25 vzpomínek; druhý dalších 25. Jedna stránka tedy
nepředstavuje kompletní zálohu (backup). Výstup JSON zachovává plné identifikátory, zatímco tabulky je mohou pro zobrazení zkrátit.

Uložení stránky do souboru:

```sh
omi --json memory list --limit 25 --offset 0 > vzpominky-stranka-1.json
```

Toto přesměrování vytvoří nebo přepíše místní soubor. Před použitím obsahu se ujistěte,
že příkaz úspěšně skončil. Chyby se zapisují do chybového výstupu (stderr); prázdný soubor
nezaručuje, že data neexistují. Exportovaný soubor může obsahovat osobní údaje: uchovávejte jej v soukromí.

## Odhlášení (Logout)

```sh
omi auth logout
```

Tento příkaz smaže místně uložené přihlašovací údaje. Pro zneplatnění klíče na serveru
použijte správu vývojářských klíčů ve svém účtu.

Další příkazy a pokročilé možnosti naleznete v [hlavní příručce v angličtině](../README.md) a spuštěním `omi --help`.
