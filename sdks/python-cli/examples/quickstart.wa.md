# Prumîs pas avou omi-cli

Li document ci vos mostere les prumîs comandes d' omi-cli e walon. Les noyés des comandes eyet les messaedjes do programe dimenèt e inglès. Les egzimpes chal n' candjrèt nén vos souvnances (memories), vos coviernaedjes (conversations), vos accions (action items), u vos ozeas (goals).

## Instalåcion

I vos fåt : Python 3.10 ou pus novea, et on conte Omi.

Si pipx est ddja-st åstallé :

```sh
pipx install omi-cli
omi --help
```

Ou dins on virtuwea environmint Python ki vos avoz-st activé :

```sh
python -m pip install omi-cli
omi --help
```

Note : li comande `omi` pout n' esse nén sol PATH come çoula — verifyîz ki l' virtuwea environmint est activé ou ki l' batchin pipx est dins `$PATH`.

## Si lôdjî

Lôdjîz vs d' abord :

```sh
omi auth login
```

Vos pôz vs lôdjî avou l' betchteu (browser) ou avou ene clé API des diswalpeus d' Omi. Tapez li clé — ele n' iret nén dins l' istwere do terminaal.

Po vs lôdjî avou l' betchteu sol mochene ci :

```sh
omi auth login --browser
```

Po des mochenes avou rén k' on terminaal : l' otorizåcion si fwait sol adresse locåle. Shuvoz les instrucions ki s' mostrèt sol waitroûle.

Verifyîz li config et l' clé API do moumint :

```sh
omi auth status
omi auth whoami
```

`status` mostere les infôrmacions locåles, i catchi les secrets, et ni dmande rén å sierveu. `whoami` evoye ene dmande acertinee ; si ça mousse, ça vout dire ki vos credinces sont bouneus.

Li config est cnåzêye dins `~/.omi/config.toml`. Ni tchatchîz nén ci fitchî a mwin — li clé et ses secrets sont divins.

## Lizte des souvnances et des coviernaedjes

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Si li lizte est vude, ça vout dire k' i n' a rén co la. Po vey les passetes (filtres) di tchaeke comande :

```sh
omi memory list --help
omi action-item list --help
```

## JSON et les ecpôrts

L' option globåle `--json` doet vnî DAVANT l' groupe di comandes :

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Li prumire comande prind les 25 prumîs souvnances ; li deujhinme prind les 25 shuvants. Li rexhowe JSON a les idintifieurs etirès, mins li tåve les rocoupe.

Po l' cnåzer dins on fitchî :

```sh
omi --json memory list --limit 25 --offset 0 > souvnances-pådje-1.json
```

Ciste redirecion ci fwait on novea fitchî locå ou rexhe l' vî. Waitroûlez l' rexhowe del comande d' abord. Les arokes vont sol stderr ; on fitchî vude ni vout nén dire k' i n' a pont d' dnêyes. Les fitchîs d' ecspôrt pôrèt avew des infôrmacions personeles — wardijhoz-les.

## Si dislôdjî

```sh
omi auth logout
```

Ciste comande ci disfa les credinces locåles. Les clés fwaites sol costé sierveu sont dizo li manaedjmint des clés di diswalpeu.

Po pus : [docs e inglès](../README.md) et `omi --help`.
