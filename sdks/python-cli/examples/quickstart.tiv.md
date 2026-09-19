# Mfe u Fese Sha Kwagh u omi-cli

Ikyur i ngeren ne ngi pasen akaawan a hiihii ken zwa Tiv sha ci u `omi-cli`. Aiti a akaawan man akaaôron a program la nga zan hemen u lun ken zwa Buter. Utese mba kengeren mba i tese heen mban vea gem m-umbur ou (memories), iliam You (conversations), aeren a i gbe u a er (action items), shin mbaawashima ou (goals) ga.

## U Nengen Sha Program (Installation)

Akaa a i gbe u u lu a mi: Python 3.10 shin u he u a hembe nahan man akaunti u Omi.

Aluer u ngu a `pipx` vough:

```sh
pipx install omi-cli
omi --help
```

U fatyô u nengen sha mi ken Python virtual environment u a lu eren tom la kpaa:

```sh
python -m pip install omi-cli
omi --help
```

Aluer i zua a icighan kwagh u `omi` ken terminal ga yô, nenge sha er virtual environment la a lu eren tom shin gbenda u `pipx` la a lu ken `$PATH` wou yô.

## U Zuan Akaa a Akaunti Wou (Authentication)

Hii or u wasen u lamen a we la:

```sh
omi auth login
```

Tsua u nyôron sha browser shin u ngeren Omi developer API key wou. Mnyer ne una yer kwaghyier la; de ngeren un ken akaawan a aa lu ken ityôkwagh i terminal la ga.

U za gbenda môm sha browser:

```sh
omi auth login --browser
```

Nyôr ken kômputa shon i môm i terminal la a lu eren tom sha mi la: mlumun u mnyer la ngu eren tom a adereshi i heem la. Dondo atindi a a lu sha skrin la.

Ken masekwagh yô, nenge sha mver man ian i kôron sha API:

```sh
omi auth status
omi auth whoami
```

`status` tese mlu u heem shi yese kwagh u myer, kpa nenge aluer ngu vough sha server ga. `whoami` tindi msen u i lumun sha mi yô; aluer a dondo vough yô, a tese er akaa ou a mnyer nga eren tom a u pasen iti You shio.

I ver akaa a mver ne sha gbaa aôndo ken `~/.omi/config.toml`. De samber a fael ne ga: una fatyô u lun a akaa a myer a vesen.

## U Kenger Akaa Ou a Ngeren (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Gbaa lisi kpa tese er ma kwagh u kenger la ngu sha kwagh u i ker la ga yô. Er tom a iwasen sha u kôron mba-tsuan ken hanma kwaghôron:

```sh
omi memory list --help
omi action-item list --help
```

## U Kôron JSON man u Pav Wegh sha Apeeji (Pagination)

Ver m-tsua u tar cii u `--json` ne **ken hemen** u gbaa akaawan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kwaghôron u hiihii la pinen m-umbur 25 mba hiihii mbara; u sha uhar la pinen 25 mba ve dondo mbara. Peeji môm tseegh ka kôpi u kuren cii (backup) ga. Akaa a JSON a dugh la nga kôsô aiti a kuren vough, nahan kpa tebur mba sha skrin vea fatyô u panden ve sha ci u mtese u kengeren.

U kôsôn peeji ken fael:

```sh
omi --json memory list --limit 25 --offset 0 > m-umbur-peeji-1.json
```

Gbenda ne ngu gbe shin gem fael u heem la. Nenge sha er kwaghôron la una kure vough cii ve u er tom a akaa a ken atô yô. Akaa a shami ga cii i nger a ken ijiir i akaa a shami ga (stderr); fael u gbaa tseegh tese er ma kwagh ngu ga ze ga. Fael u i dugh la una fatyô u lun a akaa a ou a iyol you: kôsô un tsembelee.

## U Duwen ken Akaunti (Logout)

```sh
omi auth logout
```

Kwaghôron ne pande akaa a mnyer a i kôsô heem la kera. Sha u kuren kwaghyier sha server, er tom a developer key sha akaunti wou.

Sha ci u akaawan agenegh man mba-tsuan mba seer, nenge [mfe u vesen u ken zwa Buter](../README.md) man `omi --help`.
