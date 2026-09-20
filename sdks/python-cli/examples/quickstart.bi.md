# Fes stef wetem omi-cli

Gid ia i eksplenem ol fes komand blong omi-cli long lanwis Bislama. Ol nem blong komand mo ol mesij blong program oli stap long Inglis. Ol eksampel long gid ia oli no jenisim ol memori, ol konvesesen, ol aksen aetem, no ol gol blong yu.

## Instolem

Yu nidim Python 3.10 no wan mo niu, mo wan Omi akaon.

Sapos `pipx` i stap finis:

```sh
pipx install omi-cli
omi --help
```

Olsem narafala rod, yu save instolem hem insaed long wan Python virtual envaironmen we i stap aktif:

```sh
python -m pip install omi-cli
omi --help
```

Sapos terminal i no faenem `omi`, chek se virtual envaironmen i aktif no se folda blong pipx i stap long `$PATH`.

## Konektem akaon blong yu

Statem intaraktiv login wizad:

```sh
omi auth login
```

Yu save jusum blong login wetem brausa no blong pastem wan Omi developer API ki. Intaraktiv login i haedem ki blong yu; yu mas stap kea blong no lego hem long terminal histri.

Blong login stret wetem brausa:

```sh
omi auth login --browser
```

Login long sem komputa we terminal i stap ron long hem: ansa blong ororaezesen i yusum wan lokol adres. Folem ol instrksen long skrin.

Naoia, chek konfiguresen mo API ki:

```sh
omi auth status
omi auth whoami
```

`status` i soem lokol stet mo i haedem ol sikret, be i no chekem se i stret long sava. `whoami` i mekem wan ororaezd rikwest; sapos i sukses, i konfem se kredensel blong yu oli wok, be i no soem nem blong yu.

Konfiguresen i stap long `~/.omi/config.toml`. No serem faei ia: maet i gat ol login sikret insaed.

## Lukluk long ol data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Wan empti lis i save min se i no gat data we i machim kueri ia nomo. Blong lanem ol filter blong evri komand, luk long help:

```sh
omi memory list --help
omi action-item list --help
```

## JSON aotput mo pejenesen

Putem global `--json` opsen **bifo** komand grup:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fes komand i askem fes 25 memori; sekon wan i askem nekis 25. Wan pej i no ful bakap. JSON aotput i kipim evri identifaia, be ol tebel long skrin oli save sotem olgeta blong luk.

Blong sevem wan pej long wan faei:

```sh
omi --json memory list --limit 25 --offset 0 > memori-pej-1.json
```

Redireksen ia i mekem no i raetem ova wan lokol faei. Bifo yu yusum kontent blong hem, chek se komand i finis wetem sukses. Ol eror oli go long stderr; wan empti faei i no minim se i no gat data. Ol ekspot faei oli save gat priwet infomesen: kipim olgeta sikret.

## Logaot

```sh
omi auth logout
```

Komand ia i deletem ol kredensel we i stap sev long lokol. Blong rivokem ki long sava, yusum developer ki manejmen long akaon blong yu.

Blong ol narafala komand mo ol advans opsen, luk long [Inglis mein gid](../README.md) mo `omi --help`.
