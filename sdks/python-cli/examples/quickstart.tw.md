# Anammɔn a edi kan wɔ omi-cli ho

Saa kwankyerɛ yi kyerɛ omi-cli faa a edi kan wɔ Twi kasa mu. Mmusuaeɛ ne dwumadie nsɛm no te saa ara wɔ Brɔfo kasa mu. Saa kwankyerɛ yi mu nsusueɛ no nnsesa wo adesoa, wo nkɔmmɔ, wo nnwuma anaa wo botaeɛ.

## Nhyɛmu

Ɛsɛ sɛ wowɔ Python 3.10 anaa emu foforɔ, ne Omi akontaabu.

Sɛ `pipx` wɔ hɔ deda a:

```sh
pipx install omi-cli
omi --help
```

Anaasɛ, fa to Python mfidie a ɛwɔ hɔ mu:

```sh
python -m pip install omi-cli
omi --help
```

Sɛ terminal no enhu `omi` a, hwɛ sɛ Python mfidie no rebɔ anaa pipx fa no wɔ `$PATH` mu.

## Fa wo akontaabu bɔ mu

Fi ase wɔ akontaabu bɔ mu ho:

```sh
omi auth login
```

Wubetumi de browser no abɔ mu anaasɛ fa Omi API safoa ka ho. Akontaabu bɔ mu no de wo safoa sie; hwɛ yie na ennyɛ wo terminal abakɔsɛm mu.

Sɛ wopɛ sɛ wode browser no bɔ mu tẽẽ a:

```sh
omi auth login --browser
```

Bɔ mu wɔ komputa korɔ no so a terminal no wɔ so: mmuaeɛ no de beaeɛ a ɛwɔ hɔ so di dwuma. Di akwankyerɛ a ɛwɔ screen no so.

Hwɛ nhyehyɛeɛ ne API safoa no:

```sh
omi auth status
omi auth whoami
```

`status` kyerɛ beaeɛ tebea na ɛsie kokoam nsɛm, nanso ɛnnkɔyɛ nhwɛsodeɛ wɔ server no so. `whoami` bɔ mmɔden a wɔagye atom; sɛ edi mu a, ɛkyerɛ sɛ wo tumi no yɛ adwuma, nanso ɛnkyerɛ wo din.

Nhyehyɛeɛ no wɔ `~/.omi/config.toml` mu. Mpaepa mu fael yi: ebia kokoam nsɛm wɔ mu.

## Hwɛ data no

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Din a ɛyɛ nwonkwan kyerɛ sɛ data biara nni hɔ a ɛne asɛmmisa no hyia. Sɛ wopɛ sɛ wuhu mmusuaeɛ a ɛwɔ dwumadie biara mu a, hwɛ mmoa no:

```sh
omi memory list --help
omi action-item list --help
```

## JSON adi ne krataafa nkyekyɛmu

Fa `--json` a ɛwɔ hɔ nyinaa no **ansɛm** dwumadie ho:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Dwumadie a ɛdi kan no de 25 a ɛdi kan no ba; a ɛto so mmienu no de 25 a ɛdi hɔ no ba. Krataafa koro pɛ nyin a ɛnhyɛ ma. JSON kyerɛ nsɛnkyerɛnne nyinaa, na nsɛm a ɛwɔ screen no so no taa twa so tiaa.

Sɛ wopɛ sɛ wokyerɛ krataafa bi wɔ fael mu a:

```sh
omi --json memory list --limit 25 --offset 0 > adesoa-krataafa-1.json
```

Nsakraeɛ no yɛ fael foforɔ anaasɛ ɛkyerɛw fael a ɛwɔ hɔ so. Hwɛ sɛ dwumadie no yɛɛ yie ansɛm sɛ wode emu nsɛm no bedi dwuma. Mfomsoɔ kɔ stderr so; fael hunu kyerɛ sɛ data nni hɔ. Fael a wɔayɛ no kyerɛw kokoam nsɛm: sie yie.

## Fi w'akontaabu mu

```sh
omi auth logout
```

Saa dwumadie yi yi beaeɛ a wɔasie no fi hɔ. Sɛ wopɛ sɛ woyi safoa no firi server no so a, fa API safoa nhyehyɛeɛ a ɛwɔ wo akontaabu no so di dwuma.

Hwɛ [Brɔfo kwankyerɛ kɛseɛ](../README.md) ne `omi --help` ma dwumadie foforɔ ne nhyehyɛeɛ akɛseɛ.
