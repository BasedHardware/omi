# Kòmanse ak omi-cli

Gid sa a montre premye kòmandman yo an Kreyòl Ayisyen. Non kòmandman yo ak mesaj sistèm yo rete an Angle. Egzanp lekti yo bay la a pap modifye memwa, konvèsasyon, lis aksyon oswa objektif ou yo.

## Enstale pwogram nan

Kondisyon: Python 3.10 oswa yon vèsyon ki pi resan ak yon kont Omi.

> Atansyon: Non pake a sou PyPI se **`omi-cli`**, alòske kòmandman ki egzekite apre enstalasyon an se **`omi`**. Gen yon pake diferan ki pa gen rapò ki rele `omi` sou PyPI — pa enstale pake sa a.

Si `pipx` enstale:

```sh
pipx install omi-cli
omi --help
```

Kòm altènatif, nan yon anviwònman virtyèl Python ki aktif:

```sh
python -m pip install omi-cli
omi --help
```

Si tèminal la pa jwenn `omi`, verifye si anviwònman virtyèl la aktif oswa si dosye binè `pipx` la nan `PATH` ou.

## Konekte kont ou

Lanse asistan entèaktif la:

```sh
omi auth login
```

Chwazi koneksyon pa navigatè, oswa chwazi opsyon pou kole kle API devlopè Omi an. Antre entèaktif la kache kle a; pa tape kle a nan kòmandman ki pral rete nan istwa tèminal la.

Pou konekte dirèkteman ak navigatè a:

```sh
omi auth login --browser
```

Fè koneksyon an sou menm òdinatè kote tèminal la ap kouri, paske otantifikasyon an retounen sou yon adrès lokal. Swiv enstriksyon ki parèt sou ekran an.

Apre sa, verifye konfigirasyon an ak aksè API a:

```sh
omi auth status
omi auth whoami
```

`status` montre eta lokal la epi kache sekrè yo, men li pa verifye yo ak sèvè a. `whoami` voye yon demann otantifye; siksè vle di kalifikasyon ou yo ap travay kòrèkteman.

Konfigirasyon an anrejistre pa defo nan `~/.omi/config.toml`. Pa pataje dosye sa a paske li gen kalifikasyon prive ou yo.

## Gade done ou yo

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Yon lis vid ka sèlman vle di pa gen okenn atik ki koresponn ak rechèch la. Pou konnen filtè yon kòmandman, gade èd la:

```sh
omi memory list --help
omi action-item list --help
```

## Jwenn JSON epi navige paj yo

Mete opsyon global `--json` an **anvan** gwoup kòmandman an:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Premye kòmandman an mande 25 premye dosye yo; dezyèm nan mande 25 pwochen yo. Se poutèt sa yon paj pa yon kopi konplè. Rezilta JSON kenbe idantifyan konplè yo, alòske tablo yo ka diminye yo.

Pou anrejistre yon paj nan yon fichye:

```sh
omi --json memory list --limit 25 --offset 0 > memwa-paj-1.json
```

Redireksyon sa a kreye oswa ranplase yon fichye lokal. Anvan ou sèvi ak kontni an, asire w kòmandman an te reyisi. Erè yo ekri nan stderr; yon fichye vid se pa prèv ke pa gen done. Fichye ekspòte a ka gen enfòmasyon pèsonèl: kenbe li an sekirite.

## Dekonekte (Log out)

```sh
omi auth logout
```

Kòmandman sa a retire kalifikasyon ki anrejistre lokalman yo. Pou anile yon kle sou sèvè a, sèvi ak jesyon kle devlopè nan kont ou.

Pou lòt kòmandman ak opsyon avanse, tanpri gade gid prensipal la an Angle:
[../README.md](../README.md) ak `omi --help`.
