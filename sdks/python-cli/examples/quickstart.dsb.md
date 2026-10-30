# Pšedne kšace z omi-cli

Toś ten pśewodnik wujasnja pšedne pśikaze (commands) omi-cli w dolnoserbšćinje. Mena pśikazow a zdźělenja programa wóstanu w engelšćinje. Pśikłady pytanja, kótarež se how pokazuju, njezměnjeju waše spomnjeśa (memories), waše rozgronaŕenja (conversations), waše nadawki (action items) ani waše cele (goals).

## Instalacija

Trjebne: Python 3.10 abo nowšy, a konto Omi.

Jolic maš `pipx`:

```sh
pipx install omi-cli
omi --help
```

Móžoš jen teke do aktiwnego Pythonowego wirtualnego wobwoda instalěrowaś:

```sh
python -m pip install omi-cli
omi --help
```

Jolic terminal `omi` njenamaka, zawěsć, až wirtualny wobwod źěła abo až `pipx`-zarědnik jo w `$PATH`.

## Zwězaj swój konto

Zachop interaktiwnego pomócnika:

```sh
omi auth login
```

Wubjeŕ pśizjawjenje pśez wobglědowak abo zasajźenje kluca API wuwijarja Omi. Interaktiwne zapódaśe kluc schowa; wobeń kluc do pśikaza pisaś, kótaryž se w stawiznach terminala wobchowa.

Aby direktnje k wobglědowakoju šeł:

```sh
omi auth login --browser
```

Pśizjaw se na samskem kompjuterje ako terminal: wótegrono awtentifikacije źo k lokalnej adrese. Slěduj pokazki na wobrazowce.

Pótom pśeglědaj konfiguraciju a API-pśistup:

```sh
omi auth status
omi auth whoami
```

`status` pokazujo lokalny status a schowa tajne, ale njepśeglědujo płaśiwosć na serwerje. `whoami` sćelo awtentifikowane napšašowanje; jolic se raźi, jo jasne, až pśistupne daty źěłaju, bźez to, aby se twójo mě pokazało.

Konfiguracija se pó standardźe do `~/.omi/config.toml` wobchowa. Njeźěl toś ten fajl: móžo priwatne pśistupne daty wopśimowaś.

## Pśeglědaj swóje daty

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prozna lisćina zwětšego jano wóznamjenja, až nic pytanju njewótpowědujo. Wužyj pomoc, aby filtry kuždego pśikaza namakał:

```sh
omi memory list --help
omi action-item list --help
```

## JSON a boki

Staj globalnu opciju `--json` **pśed** pśikaznej skupinu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pśedny pśikaz se 25 pśednych spomnjeśow wupšaša; drugi pśiducy 25. Jaden bok dopołna kopija njejo. JSON-wudaśe cełe numery wobchowa, mjaztym tabele na wobrazowce mógu je skrotśiś.

Aby bok do fajla składował:

```sh
omi --json memory list --limit 25 --offset 0 > spomnjeśa-bok-1.json
```

Toś to pśesměrowanje lokalny fajl napórajo abo pśepisujo. Zawěsć, až pśikaz jo gótowy, pjerwjej až wopśimjeśe wužywaš. Zmólki se do zmólkowego wudaśa (stderr) pisaju; prozny fajl dokaz za to njejo, až daty njejsu. Eksportowany fajl móžo wósobne informacije wopśimowaś: wobchowaj jen priwatnje.

## Wótzjawjenje

```sh
omi auth logout
```

Toś ten pśikaz wušmórnjo lokalnje składowane pśistupne daty. Aby kluc na serwerje znjemóžnił, wužyj rědowanje wuwijarskich klucow w swójom konśe.

Za dalšne pśikaze a opcije glej [głowny pśewodnik w engelšćinje](../README.md) a `omi --help`.
