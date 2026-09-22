# Mikangidulu ya ntete ti omi-cli

Nkanda yai ke yasola mikangidulu ya ntete (commands) ya omi-cli na Kikongo. Bazina ya mikangidulu ye bansangu ya programe ke bikala na Kingelesi. Bambandu ya kusosa ya kutala mu yai ke basobola ve kusoba bidimbu na nge (memories), masolo na nge (conversations), bisalu na nge (action items) to minkanu na nge (goals).

## Kutula

Mambu ya mfunu: Python 3.10 to ya mpa, ye konti ya Omi mosi.

Kana nge kele ti `pipx`:

```sh
pipx install omi-cli
omi --help
```

Nge lenda tula mpe na kati ya virtual environment ya Python yina ke salama:

```sh
python -m pip install omi-cli
omi --help
```

Kana terminal ke monaka ve `omi`, bakisa nde virtual environment ke salama to nde folder ya `pipx` kele na `$PATH`.

## Kukangidisa konti na nge

Kutalisa nsadisi ya masolo:

```sh
omi auth login
```

Sola kukota na browser to kubaka kiyi ya API ya Omi developer. Kukota ya masolo ke bumba kiyi yina; buya kusonika yo na kati ya mukangidulu yina ke bikala na nkanda ya micu ya terminal.

Sambu na kukwenda mbala mosi na browser:

```sh
omi auth login --browser
```

Kota na komputadora yina kele ti terminal: mvutu ya kudiyala ke kwenda na adrese ya kisika. Landa malongi ya kele na ekrana.

Na nima, talisa mbandu ya kusala ye kukota ya API:

```sh
omi auth status
omi auth whoami
```

`status` ke monisa mbandu ya kisika ye ke bumba sekele, kansi ke talisaka ve kuvanda ya mbote na server. `whoami` ke sala luzayisu ya kudiyala; kana yo nunguka, yo ke monisa nde banzikisa ke salama, kukonda kumonisa nkumbu na nge.

Mbandu ya kusala ke bokama na default na `~/.omi/config.toml`. Kabula ve nkanda yai: yo lenda vanda ti banzikisa ya nsoni.

## Kutala bansiku na nge

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Liste ya mpamba ke tendula mbala mingi nde ata kima ke wakana ve ti kusosa. Sadila lusadisu sambu na kumona bafiltre ya konso mukangidulu:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ye mabaya

Tula mbendi ya ntoto yonso `--json` **na ntwala** ya kimvuka ya mikangidulu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Mukangidulu ya ntete ke lomba bidimbu 25 ya ntete; ya zole ke lomba 25 ya kelanda. Laya mosi kele ve kopi ya kukuka. JSON ke bumba bantalu ya mvimba, kansi bamesa ya ekrana lenda kufwisa yo.

Sambu na kubumba laya na nkanda:

```sh
omi --json memory list --limit 25 --offset 0 > bidimbu-laya-1.json
```

Kubalula yai ke sala to ke sonika nkanda ya kisika. Bakisa nde mukangidulu me manaka na ntwala ya kusadila mambu na kati. Mafuku ke sonikama na mbendi ya mafuku (stderr); nkanda ya mpamba kele ve kidimbu nde data kele ve. Nkanda ya kubasisa lenda vanda ti bansangu ya muntu: bumba yo na nsoni.

## Kubasika

```sh
omi auth logout
```

Mukangidulu yai ke katula banzikisa ya kubumba ya kisika. Sambu na kukatula kiyi na server, sadila kutwadisa kiyi ya developer na konti na nge mosi.

Sambu na mikangidulu ye mbendi ya nkaka, tala [nkanda ya nene na Kingelesi](../README.md) ye `omi --help`.
