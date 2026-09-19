# Mulai Capek mamakai omi-cli

Panduan ko manjalangan parentah-parentah dasar dalam baso Minangkabau (Baso Minang). Namo parentah jo pasan dari program tatap mamakai baso Inggirih. Contoh pamarisoan (query) di bawah ko indak maubah ingek-ingekan (memories), pasan bual (conversations), karajoan (action items), atau tujuan (goals) sanak.

## Mamasang program

Syarat: Python 3.10 atau versi nan labiah baru sarato akun Omi.

Jikok sanak alah mamasang `pipx`:

```sh
pipx install omi-cli
omi --help
```

Sabagai piliahan lain, sanak dapek mamasang di dalam virtual environment Python nan sadang aktif:

```sh
python -m pip install omi-cli
omi --help
```

Jikok terminal indak basuo `omi`, pastian virtual environment alah aktif atau folder tampek `pipx` manyimpan berkas eksekusi alah tacantum dalam `$PATH` sanak.

## Manyambuang akun sanak

Jalanan asisten interaktif:

```sh
omi auth login
```

Piliahlah masuak malalui browser atau tempelkan kunci API pambuek Omi. Input interaktif manyuruakan kunci; jan tulih kunci dalam parentah nan ka tasimpan dalam riwayaik terminal.

Untuak langsuang mamakai browser:

```sh
omi auth login --browser
```

Masuak di komputer nan samo jo tampek terminal bajalan: jawaban autentikasi mamakai alamat lokal. Ikuikan panduan di layar.

Salasai tu, pariso konfigurasi jo akses API:

```sh
omi auth status
omi auth whoami
```

`status` manampakan kaadaan lokal jo manyuruakan rahasio, tapi indak mamariso kasahannyo di server. `whoami` mangirim pamintaan nan alah diautentikasi; jikok barasil, iko mambuktian baso kredensial dapek digunokan tanpa paralu manampakan namo sanak.

Sacaro baku konfigurasi tasimpan di `~/.omi/config.toml`. Jan agiah tau berkas ko ka urang lain dek karano dapek barisi kredensial rahasio sanak.

## Mamariso data sanak

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daftar nan kosong dapek baarti indak ado barang nan sasuai jo panyariang. Gunokan bantuan untuak mancaliak panyariang di satiok parentah:

```sh
omi memory list --help
omi action-item list --help
```

## Maambiak JSON jo bapindah laman (Pagination)

Latak-an piliahan global `--json` **sabalun** kalompok parentah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Parentah partamo mamintak 25 ingek-ingekan partamo; parentah kaduo, 25 salanjuiknyo. Salaman indaklah cadangan nan langkok. Kaluaran JSON manyimpan tando pangana sacaro panuah, samantaro tabel di layar dapek mampasingkeknyo untuak rancak dicaliak.

Untuak manyimpan salaman ka dalam ciek berkas:

```sh
omi --json memory list --limit 25 --offset 0 > ingek-ingekan-laman-1.json
```

Pangaliahan ko mambuek atau mangganti berkas lokal. Pastian parentah salasai sacaro elok sabalun mamakai isinyo. Kasalahan tatulih ka kaluaran kasalahan (stderr); berkas nan kosong indak manjamin baso indak ado data. Berkas nan diekspor dapek barisi informasi pribadi: simpanlah jo aman.

## Kalua dari akun (Logout)

```sh
omi auth logout
```

Parentah ko mangapuih kredensial nan tasimpan sacaro lokal. Untuak mambatalan kunci di server, gunokan pangaturan kunci pambuek di akun sanak.

Untuak parentah lain sarato piliahan nan labiah langkok, caliak [panduan utamo dalam baso Inggirih](../README.md) jo `omi --help`.
