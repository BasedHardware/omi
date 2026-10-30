# Langkah Kapertama sareng omi-cli

Pituduh puniki ngelimbakang tata cara (commands) kapertama omi-cli ring basa Bali. Parinama tata cara miwah pisarat program tetep nganggen basa Inggris. Conto panureksa sane kacihnayang iriki nenten nguwah memori (memories), pabaosan (conversations), pakaryan (action items), utawi tatujon (goals) ragane.

## Pamasangan

Sane kabetahang: Python 3.10 utawi langkungan, miwah akun Omi.

Yening ragane medue `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ragané taler prasida ngunggahang punika ring virtual environment Python sane aktif:

```sh
python -m pip install omi-cli
omi --help
```

Yening terminal nenten nemu `omi`, pastikang virtual environment punika aktif utawi folder `pipx` punika ring `$PATH`.

## Nyambungang akun

Ngawitin asisten interaktif:

```sh
omi auth login
```

Pilih login malarapan browser utawi nempelang Omi developer API key. Input interaktif nyengkeré key punika; eda nulis key punika ring tata cara sane kapupu ring sajeroning terminal history.

Yening jagi langsung ka browser:

```sh
omi auth login --browser
```

Login ring komputer sane pateh sareng terminal: pasaur autentikasi nuju ka alamat lokal. Tureksin pituduh ring layar.

Sasampune punika, verifikasi konfigurasi miwah akses API:

```sh
omi auth status
omi auth whoami
```

`status` ngenyodayang kahanan lokal miwah nyengkeré rahasia, nanging nenten ngeverifikasi validitas ring server. `whoami` ngaryanin panyuwunan autentikasi; yening hasil, jelas indik kredensial punika nganggen, tanpa ngenyodayang wasta ragane.

Konfigurasi kasimpen manut default ring `~/.omi/config.toml`. Eda nyobyahang file puniki: prasida madaging kredensial rahasia.

## Ngiderin data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lis kosong ketahnyane maartos nenten wenten sane cocok sareng panureksa. Anggen bantuan punika mangda nemu filter saking soang-soang tata cara:

```sh
omi memory list --help
omi action-item list --help
```

## JSON miwah kaca

Genahang opsi jagat `--json` **sadurung** kelompok tata cara:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Tata cara kapertama nglungsur 25 memori kapertama; sane kaping kalih nglungsur 25 salanturnyane. Asiki kaca nenten salinan jangkep. Output JSON nyaga angka utuh, sakewanten tabel ring layar prasida nyinekang punika.

Jagi nyimpen kaca ring file:

```sh
omi --json memory list --limit 25 --offset 0 > memori-kaca-1.json
```

Redirect puniki ngaryanin utawi nyurat malih file lokal. Pastikang tata cara punika puput sadurung nganggen isinyane. Pikobet kaserat ka output pikobet (stderr); file kosong nenten bukti nenten wenten data. File sane kaekspor prasida madaging informasi pribadi: simpen punika rahasia.

## Medal

```sh
omi auth logout
```

Tata cara puniki mbusan kredensial sane kasimpen lokal. Jagi ngewangdé key ring server, anggen pangaturan developer key ring akun ragane padidi.

Antuk tata cara miwah opsi lianan, tureksin [pituduh utama basa Inggris](../README.md) miwah `omi --help`.
