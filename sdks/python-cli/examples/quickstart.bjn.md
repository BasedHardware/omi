# Bamula Lakas mamakai omi-cli

Panduan ngini manjalasakan parintah-parintah dasar dalam basa Banjar (Bahasa Banjar). Ngaran parintah wan pasan matan program tatap mamakai basa Inggiris. Cuntuh pamariksaan (query) di bawah ngini kada maubah ingatan (memories), panderan (conversations), gawian (action items), atawa tujuan (goals) pian.

## Manatapakan program

Syarat: Python 3.10 atawa versi nang labih hanyar wan akun Omi.

Amun pian sudah mamasang `pipx`:

```sh
pipx install omi-cli
omi --help
```

Sabagai pilihan lain, pian kawa mamasang di dalam virtual environment Python nang lagi aktif:

```sh
python -m pip install omi-cli
omi --help
```

Amun terminal kada tatamu `omi`, pastiakan virtual environment sudah aktif atawa folder wadah `pipx` manyimpan berkas eksekusi sudah ada di dalam `$PATH` pian.

## Manyambungakan akun pian

Jalanakan asisten interaktif:

```sh
omi auth login
```

Pilih masuk liwat browser atawa tempelakan kunci API paulah Omi. Input interaktif manyungkupakan kunci; jangan manulis kunci di dalam parintah nang kawa takait di riwayat terminal.

Gasan langsung mamakai browser:

```sh
omi auth login --browser
```

Masuk di kumputer nang sama wan wadah terminal bajalan: jawaban autentikasi mamakai alamat lokal. Turuti patunjuk di layar.

Imbah ngitu, pariksa konfigurasi wan jalan masuk API:

```sh
omi auth status
omi auth whoami
```

`status` manampaiakan kaadaan lokal wan manyungkupakan rahasia, tagal kada mamariksa bujur kada-nya di server. `whoami` mangirim pamintaan nang sudah diautentikasi; amun bahasil, ngini mambuktiakan kredensial kawa dipakai kada parlu manampaiakan ngaran pian.

Biasanya konfigurasi disimpan di `~/.omi/config.toml`. Jangan dibagikan berkas ngini maraga kawa maingkut kredensial rahasia pian.

## Mamariksa data pian

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daftar nang puang kawa haja baarti kadada barang nang pas wan panyaring. Pakai bantuan gasan manjanaki panyaring di saban parintah:

```sh
omi memory list --help
omi action-item list --help
```

## Maambil JSON wan ba-alih laman (Pagination)

Andak pilihan global `--json` **sabalum** garumbung parintah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Parintah panambayan maminta 25 ingatan pamulaan; parintah kadua, 25 imbahnya. Sahalaman lainan cadangan nang langkap. Kaluaran JSON manyimpan tanda idintifikasi sacara langkap, amun tabel di layar kawa mamandakakan gasan kancangan janak.

Gasan manyimpan sahalaman ka dalam sabuah berkas:

```sh
omi --json memory list --limit 25 --offset 0 > ingatan-laman-1.json
```

Pangaliahan ngini maulah atawa mangganti berkas lokal. Pastiakan parintah tuntung sacara bujur sabalum mamakai isinya. Kasalahan tatulis ka kaluaran salah (stderr); berkas nang puang lainan jaminan kadada data. Berkas nang diekspor kawa maingkut habar pribadi: simpan bujur-bujur.

## Kaluar matan akun (Logout)

```sh
omi auth logout
```

Parintah ngini mahapus kredensial nang disimpan sacara lokal. Gasan mambatalakan kunci di server, pakai paaturan kunci paulah di akun pian.

Gasan parintah lain wan pilihan nang labih langkap, itihi [panduan utama dalam basa Inggiris](../README.md) wan `omi --help`.
