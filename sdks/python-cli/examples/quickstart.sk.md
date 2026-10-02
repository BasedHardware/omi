# Prvé kroky s omi-cli

Tento sprievodca vysvetľuje prvé príkazy v slovenskom jazyku. Názvy príkazov a
správy programu zostávajú v angličtine. Príklady dopytov uvedené v tomto návode
nemenia vaše spomienky, konverzácie, úlohy ani ciele.

## Inštalácia programu

Požiadavky: Python 3.10 alebo novšia verzia a účet Omi.

Ak máte nainštalovaný `pipx`:

```sh
pipx install omi-cli
omi --help
```

Prípadne ho môžete nainštalovať v aktivovanom virtuálnom prostredí Python:

```sh
python -m pip install omi-cli
omi --help
```

Ak terminál nenájde `omi`, skontrolujte, či je virtuálne prostredie aktivované
alebo či sa adresár, do ktorého `pipx` inštaluje spustiteľné súbory, nachádza vo vašom `PATH`.

## Pripojenie účtu

Spustite interaktívneho sprievodcu:

```sh
omi auth login
```

Vyberte prihlásenie cez prehliadač alebo možnosť vložiť vývojársky API kľúč Omi.
Interaktívny vstup skryje kľúč; vyhnite sa jeho písaniu do príkazu, ktorý zostane v histórii terminálu.

Pre priamy prechod do prehliadača:

```sh
omi auth login --browser
```

Prihláste sa na rovnakom počítači, na ktorom beží terminál: autentifikačná odpoveď
používa lokálnu adresu. Postupujte podľa pokynov na obrazovke.

Potom overte konfiguráciu a prístup k API:

```sh
omi auth status
omi auth whoami
```

`status` zobrazuje lokálny stav a skrýva tajomstvo, ale neoveruje platnosť na serveri.
`whoami` odošle overenú požiadavku; ak uspeje, potvrdí funkčnosť prihlasovacích údajov bez toho, aby nutne zobrazoval vaše meno.

Konfigurácia sa predvolene ukladá do `~/.omi/config.toml`. Nezdieľajte tento súbor:
môže obsahovať vaše dôverné prihlasovacie údaje.

## Zobrazenie vašich údajov

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prázdny zoznam môže jednoducho znamenať, že žiadne položky nezodpovedajú dopytu.
Pomocou pomocníka zistíte filtre pre každý príkaz:

```sh
omi memory list --help
omi action-item list --help
```

## Získanie JSON a navigácia po stránkach

Umiestnite globálnu voľbu `--json` **pred** skupinu príkazov:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prvý príkaz požiada o prvých 25 spomienok; druhý o ďalších 25. Jedna stránka teda
nie je úplnou zálohou (backup). Výstup JSON zachováva úplné identifikátory, zatiaľ čo tabuľky ich môžu skrátiť na zobrazenie.

Uloženie stránky do súboru:

```sh
omi --json memory list --limit 25 --offset 0 > spomienky-stranka-1.json
```

Toto presmerovanie vytvorí alebo prepíše lokálny súbor. Pred použitím obsahu sa uistite,
že príkaz úspešne skončil. Chyby sa zapisujú do chybového výstupu (stderr); prázdny súbor
nezaručuje, že neexistujú žiadne údaje. Exportovaný súbor môže obsahovať osobné údaje: uchovávajte ho v súkromí.

## Odhlásenie (Logout)

```sh
omi auth logout
```

Tento príkaz vymaže lokálne uložené prihlasovacie údaje. Ak chcete odvolať kľúč na serveri,
použite správu vývojárskych kľúčov vo svojom účte.

Ďalšie príkazy a pokročilé možnosti nájdete v [hlavnom návode v angličtine](../README.md) a `omi --help`.
