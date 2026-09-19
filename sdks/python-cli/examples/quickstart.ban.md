# Ngawit nganggen omi-cli

Pituduh puniki nyinahang makudang-kudang pamargin kapertama ring Basa Bali. Wasta pamargin miwah orti sistem tetep ring Basa Inggris. Conto ngwacen sane kaicenin iriki nenten pacang nguwah elingan, pabligbagan, lis parikrama utawi tatujon ragane.

## Masang program

Kaperluan: Python 3.10 utawi versi anyar miwah akun Omi.

> Uratiang: Wasta paket ring PyPI inggih punika **`omi-cli`**, nanging pamargin sane mamargi risampune kapasang inggih punika **`omi`**. Wenten paket sios sane nenten mapaiketan mawasta `omi` ring PyPI — sampunang masang paket punika.

Yening `pipx` sampun kapasang:

```sh
pipx install omi-cli
omi --help
```

Tiosan punika, ring palemahan virtual Python sane maurip:

```sh
python -m pip install omi-cli
omi --help
```

Yening terminal nenten ngamolihang `omi`, pastikayang palemahan virtual punika maurip utawi direktori `pipx` wenten ring `PATH` ragane.

## Nyambungang akun ragane

Kawitin panulung interaktif:

```sh
omi auth login
```

Pilih ngranjing nganggen peramban web, utawi pilih pilihan anggen nancepang kunci API panglimbak Omi. Masukan interaktif nylemsimang kuncine; sampunang nyurat kunci ring pamargin sane pacang megenah ring babad terminal.

Yening ngranjing langsung saking peramban:

```sh
omi auth login --browser
```

Puputang ngranjing ring komputer sane pateh ring dija terminal punika mamargi, santukan validasi punika mawali ring genah lokal. Tutug pituduh ring layar.

Risampune punika, tegarang selehin konfigurasi miwah pamargi nuju API:

```sh
omi auth status
omi auth whoami
```

`status` nyinahang kahanan lokal miwah nylemsimang rahasia, nanging nenten ngamastikayang ring server. `whoami` ngirim pinunas sane ma-otentikasi; kasuksesan mateges bukti pamargi ragane mamargi patut.

Konfigurasi puniki kasimpen ring `~/.omi/config.toml`. Sampunang nyobyahang berkas puniki santukan madaging bukti pamargi pribadi ragane.

## Nyingakin data ragane

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lis sane puyung prasida mateges nenten wenten sane manut ring pinunas punika. Anggen ngresepang saringan pamargin, cingak pitulung:

```sh
omi memory list --help
omi action-item list --help
```

## Ngamolihang JSON miwah nyliksik kaca

Genahang pilihan universal `--json` **sadurung** pupulan pamargin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pamargin kapertama nunas 25 catatan kapertama; sane kaping kalih nunas 25 catatan salanturnyane. Punika mawinan sakaca nenten dados cadangan sane jangkep. Asil JSON nyimpen wasta sane jangkep, nanging tabel prasida nyendekang.

Anggen nyimpen sakaca ring berkas:

```sh
omi --json memory list --limit 25 --offset 0 > elingan-kaca-1.json
```

Pangentos puniki ngardi utawi ngentosin berkas lokal. Sadurung nganggen dagingnyane, pastikayang pamargin punika sampun labda karya. Kapiambeng kasurat ring stderr; berkas sane puyung boya ja bukti nenten wenten data. Berkas sane kasimpen prasida madaging data pribadi: simpen becik-becik.

## Medal (Log out)

```sh
omi auth logout
```

Pamargin puniki ngicalang bukti pamargi sane kasimpen ring lokal. Anggen ngesahang kunci ring server, anggen pamargin kunci panglimbak ring akun ragane.

Anggen pamargin lianan miwah pilihan sane canggih, durus cingak pituduh utama ring Basa Inggris:
[../README.md](../README.md) miwah `omi --help`.
