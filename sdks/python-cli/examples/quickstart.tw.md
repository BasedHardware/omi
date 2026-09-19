# Mfitiaseɛ wɔ omi-cli ho

Saa akwankyerɛ yi kyerɛ mmara a edi kan kakra wɔ Twi kasa mu. Mmara din ne nhyehyɛe nkra no bɛkɔ so ayɛ Borɔfo kasa. Akenkan mfatoho a wɔde ama wɔ ha no rensesa w'akaeɛ, nkɔmmɔbɔ, nneyɛe din anaa botae ahorow.

## Fa dwumadie no hyɛ mu

Nea ɛho hia: Python 3.10 anaa nea ɛyɛ foforo ne Omi akontaabuo.

> Hyɛ no nso: PyPI so mfididwuma din ne **`omi-cli`**, bere a mmara a ɛbɛdi dwuma bere a wɔde ahyɛ mu akyi ne **`omi`**. Mfididwuma foforɔ bi a ɛnte saa a wɔfrɛ no `omi` wɔ PyPI so — mfa saa mfididwuma no nhyɛ mu.

Sɛ wɔde `pipx` ahyɛ mu a:

```sh
pipx install omi-cli
omi --help
```

Sɛ ɛnte saa nso a, wɔ Python virtual environment a ɛreyɛ adwuma mu:

```sh
python -m pip install omi-cli
omi --help
```

Sɛ terminal no nhu `omi` a, hwɛ sɛ virtual environment no reyɛ adwuma anaa `pipx` nhyehyɛe no wɔ wo `PATH` mu.

## Fa wo akontaabuo bata ho

Fi ase interaktiv mmoa:

```sh
omi auth login
```

Paw sɛ wobɛkɔ mu denam browser so, anaa paw kwan a wobɛfa so atow Omi yɛfo API safe akyi. Nsɛmfua a wɔde hyɛ mu no de safe no sie; ntwerɛ safe no wɔ mmara a ɛbɛka terminal abakɔsɛm mu no mu.

Sɛ wobɛkɔ mu tẽẽ denam browser so a:

```sh
omi auth login --browser
```

Wie kɔ mu no wɔ afidie koro a terminal no reyɛ adwuma wɔ so no so, efisɛ adansedie no san ba mpɔtam hɔ kwan so. Di akwankyerɛ a ɛwɔ skrin so no akyi.

Ɛno akyi no, hwɛ nhyehyɛe ne API kwan a wobɛfa so akɔ:

```sh
omi auth status
omi auth whoami
```

`status` kyerɛ mpɔtam hɔ gyinabea na ɛde ahintasɛm sie, nanso ɛnhwɛ server no so. `whoami` soma abisadeɛ a wɔagye atom; nkonimdi kyerɛ sɛ w'adansedie nyinaa reyɛ adwuma yiye.

Wɔkora nhyehyɛe no so wɔ `~/.omi/config.toml` mu. Mfa saa fael yi mma afoforo efisɛ ɛkura wo kokoamsɛm mu adansedie.

## Hwɛ wo nkyerɛwee

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Krataafa a hwee nni so betumi akyerɛ kɛkɛ sɛ biribiara nni hɔ a ɛne abisade no hyia. Sɛ wopɛ sɛ wote mmara bi nsonsonoe ase a, hwɛ mmoa no:

```sh
omi memory list --help
omi action-item list --help
```

## Gye JSON na fa kratafa so kɔ

Fa amansan kwan `--json` no si mmara kuw no **anim**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Mmara a edi kan no bisa nkrataa 25 a edi kan; nea ɛto so mmienu no bisa 25 a edi hɔ no. Enti kratafa koro nnyɛ kɔpi a edi mu. JSON fipono no kura nkyerɛkyerɛmu a edi mu, bere a mpon betumi atwitwa so.

Sɛ wobɛkora kratafa bi so wɔ fael bi mu a:

```sh
omi --json memory list --limit 25 --offset 0 > nkaee-kratafa-1.json
```

Saa kwan foforɔ yi bɔ anaa ɛsesa mpɔtam hɔ fael bi. Ansa na wobɛfa emu nsɛm adi dwuma no, hwɛ sɛ mmara no dii nkonim. Wɔtwere mfomso ahorow gu stderr so; fael a hwee nni mu nkyerɛ sɛ nkyerɛwee biara nni hɔ. Fael a wɔakora so no betumi akura wo kokoamsɛm: fa sie yiye.

## Piri firi mu (Log out)

```sh
omi auth logout
```

Saa mmara yi yi adansedie a wɔakora so wɔ mpɔtam hɔ no fi hɔ. Sɛ wopɛ sɛ wogyae safe bi a ɛwɔ server no so a, fa mfididwumayɛfo safe sohwɛ a ɛwɔ wo akontaabuo mu no di dwuma.

Sɛ wopɛ mmara foforo ne kwan a ɛkɔ akyiri a, yɛsrɛ wo hwɛ Borɔfo akwankyerɛ titiriw no:
[../README.md](../README.md) ne `omi --help`.
