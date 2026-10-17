# Kòmanse rapidman ak omi-cli

Gid sa a eksplike kòmand debaz yo an kreyòl ayisyen. Non kòmand yo ak mesaj
pwogram lan rete an anglè. Egzanp kòmand yo pa modifye souvni, konvèsasyon,
atòm aksyon, oswa objektif ou yo.

## Enstale pwogram nan

Kondisyon: Python 3.10 oswa pi resan ak yon kont Omi.

Si `pipx` deja enstale:

```sh
pipx install omi-cli
omi --help
```

Oubyen enstale l nan yon anviwònman vityèl Python ki aktive:

```sh
python -m pip install omi-cli
omi --help
```

Si tèminal la pa jwenn `omi`, verifye anviwònman vityèl la aktive oswa ke
anyè kote `pipx` mete fichye egzekitabl yo sou `PATH`.

## Konekte kont ou

Kouri gid entèraktif la:

```sh
omi auth login
```

Chwazi login nan navigatè oswa kole yon kle API devlopè Omi. Antre
entèraktif la kache kle a; pa tape l nan kòmand ki sove nan istorik
tèminal la.

Pou itilize navigatè dirèkteman:

```sh
omi auth login --browser
```

Konekte sou menm òdinatè ak tèminal la paske otantifikasyon an sèvi ak yon
adrès callback lokal. Swiv enstriksyon ki parèt sou ekran.

Apre login, tcheke konfigirasyon ak aksè API a:

```sh
omi auth status
omi auth whoami
```

`status` montre eta lokal la epi maske sekrè, men li pa verifye validite yo
sou sèvè a. `whoami` voye yon demann otantifye; si li reyisi, kredansyèl ou
yo mache san montre non ou.

Konfigirasyon an sove nan `~/.omi/config.toml` pa default. Pa pataje fichye
sa a — li ka gen kredansyèl ladan.

## Li done ou yo

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Yon lis vid ka vle di pa gen atik ki matche ak filtè a. Gade opsyon chak
kòmand nan èd la:

```sh
omi memory list --help
omi action-item list --help
```

## Jwenn JSON epi navige paj yo

Mete opsyon global `--json` la **avan** gwoup kòmand lan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Premye kòmand lan mande 25 premye souvni yo; dezyèm lan mande 25 swivan yo.
Yon paj se pa yon backup konplè. Sòti JSON la kenbe ID konplè yo, pandan
tablo a ka koute ID yo pou afichaj.

Pou sove yon paj nan yon fichye:

```sh
omi --json memory list --limit 25 --offset 0 > memwa-paj-1.json
```

Redirect sa a kreye oswa ranplase yon fichye lokal. Verifye kòmand lan te
fini san erè anvan ou itilize kontni an. Erè yo ale sou stderr; yon fichye
vid pa pwouve pa gen done. Fichye ekspò a ka gen enfòmasyon pèsonèl — kenbe l
prive.

## Itilize pwofil yo

Eta a sove nan `~/.omi/config.toml` (ka chanje ak `$OMI_CONFIG`). Chak pwofil
gen pwòp metòd otantifikasyon ak adrès API. Chanje pwofil ak `--profile`:

```sh
omi config profile use travay
omi auth login
omi --profile prive memory list
```

Kòmand konfigirasyon ki komen:

```sh
omi config show
omi config path
omi config profile list
```

## Kod sòti

Kod sòti sa yo estab epi itil pou script oswa ajan:

| Kod | Siyifikasyon | Egzanp sitiyasyon |
| ---: | --- | --- |
| 0 | siksè | Kòmand lan fini |
| 1 | erè itilizasyon | Move flag, agiman manke oswa validasyon echwe |
| 2 | erè otantifikasyon | Kredansyèl pa la, token ekspire oswa dwa manke |
| 3 | erè sèvè | Sèvè 5xx oswa koneksyon echwe |
| 4 | limit vitès | Sèvè a te retounen HTTP 429 |
| 5 | pa jwenn | Sèvè a te retounen HTTP 404 |

## Dekonekte

```sh
omi auth logout
```

Sa retire kredansyèl ki sove lokalman. Pou revoke kle a sou sèvè a, itilize
jesyon kle devlopè nan kont ou.

Pou plis kòmand ak opsyon, gade [README prensipal an anglè](../README.md)
epi kouri `omi --help`.
