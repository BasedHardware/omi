# Anammɔn a edi kan ne omi-cli

Saa akwankyerɛ yi kyerɛ omi-cli mmara a edi kan (commands) wɔ Twi kasa mu. Mmara no din ne ɔman no nkrasɛm bɛyɛ Borɔfo kasa mu. Nhwehwɛmu nhwɛso a wɔakyerɛ wɔ ha no nnsesa wo nkae (memories), wo nkɔmmɔ (conversations), wo nnwuma (action items) anaa wo botae (goals).

## Nhyehyɛe

Nea ehia: Python 3.10 anaa nea ɛboro saa, ne Omi akontaabu bi.

Sɛ wowɔ `pipx` a:

```sh
pipx install omi-cli
omi --help
```

Wobetumi nso de asi Python mfirihyia mu (virtual environment) a ɛreyɛ adwuma:

```sh
python -m pip install omi-cli
omi --help
```

Sɛ terminal no anhu `omi` a, hwɛ yie sɛ virtual environment no reyɛ adwuma anaasɛ `pipx` folder no wɔ `$PATH` mu.

## Fa wo akontaabu bɔ mu

Fi ase ne ɔboafo a ɔne wo di nkɔmmɔ (interactive assistant) no:

```sh
omi auth login
```

Paw sɛ wobɛkɔ mu wɔ browser so anaasɛ wobɛfa Omi developer API safoa. Interactive input no sie safoa no; kwati sɛ wobɛkyerɛw safoa no wɔ mmara bi mu a wɔbɛkora so wɔ terminal abakɔsɛm mu.

Sɛ wopɛ sɛ wokɔ browser so tẽẽ a:

```sh
omi auth login --browser
```

Kɔ mu wɔ computer korɔ no ara so a terminal no wɔ so: authentication mmuae no kɔ local address no so. Di nsɛm a ɛwɔ screen no so.

Akyi no, hwɛ sɛ nhyehyɛe no ne API kwan no yɛ adwuma:

```sh
omi auth status
omi auth whoami
```

`status` kyerɛ local tebea no na ɛsie kokoam nsɛm no, nanso ɛnhwɛ sɛ ɛyɛ adwuma wɔ server no so. `whoami` yɛ authenticated abisade; sɛ ɛyɛ yie a, ɛkyerɛ sɛ wo nsɛm no yɛ adwuma, na ɛnkyerɛ wo din.

Wɔkora nhyehyɛe no so sɛ default wɔ `~/.omi/config.toml`. Mpaepaemu saa file yi: ebetumi anya kokoam nsɛm.

## Hwɛ wo data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

List a ɛyɛ hwee kyerɛ sɛ biribiara nhyia wo nhwehwɛmu no. Fa mmoa no di dwuma na hu filter ahorow a ɛwɔ mmara biara mu:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ne krataafa

Fa wiase nyinaa option `--json` to **anim** wɔ mmara kuw no:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Mmara a edi kan no bisa nkae 25 a edi kan; nea ɛto so abien bisa 25 a ɛdi hɔ. Krataafa biako nyɛ backup a edi mũ. JSON output no kora ankonam nɔma so, nanso table a ɛwɔ screen no betumi atwa mu.

Sɛ wopɛ sɛ wokora krataafa bi wɔ file mu a:

```sh
omi --json memory list --limit 25 --offset 0 > nkae-krataafa-1.json
```

Saa redirect yi bɔ file foforo anaasɛ ɛsan kyerɛw nea ɛwɔ mu. Hwɛ yie sɛ mmara no wie ansa na wode nea ɛwɔ mu no adi dwuma. Mfomso wɔkyerɛw wɔ error output (stderr) mu; file a ɛyɛ hwee nyɛ adansedie sɛ data nni hɔ. File a wotuu fii mu betumi anya wo ankasa nsɛm: sie no kokoam.

## Fi mu kɔ

```sh
omi auth logout
```

Saa mmara yi pepa nsɛm a wɔkora so wɔ local no fi mu. Sɛ wopɛ sɛ wopa safoa no wɔ server no so a, fa developer safoa nhwɛso a ɛwɔ wo akontaabu no mu no di dwuma.

Ma mmara ne option pii no, hwɛ [Borɔfo akwankyerɛ titiriw no](../README.md) ne `omi --help`.
