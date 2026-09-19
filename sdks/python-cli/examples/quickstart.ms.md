# Bermula dengan omi-cli

Panduan ini menunjukkan beberapa arahan pertama dalam Bahasa Melayu. Nama arahan dan mesej program kekal dalam bahasa Inggeris. Contoh bacaan yang diberikan di sini tidak akan mengubah ingatan, perbualan, senarai tindakan atau matlamat anda.

## Pasang program

Keperluan: Python 3.10 atau versi lebih baharu dan akaun Omi.

> Perhatian: Nama pakej di PyPI ialah **`omi-cli`**, manakala arahan yang dijalankan selepas pemasangan ialah **`omi`**. Terdapat pakej berbeza yang tidak berkaitan bernama `omi` di PyPI — jangan pasang pakej tersebut.

Jika `pipx` dipasang:

```sh
pipx install omi-cli
omi --help
```

Sebagai alternatif, dalam persekitaran maya Python yang aktif:

```sh
python -m pip install omi-cli
omi --help
```

Jika terminal tidak menemui `omi`, pastikan persekitaran maya aktif atau direktori binari `pipx` berada dalam `PATH` anda.

## Sambungkan akaun anda

Mulakan pembantu interaktif:

```sh
omi auth login
```

Pilih log masuk melalui pelayar, atau pilih pilihan untuk menampal kunci API pembangun Omi. Input interaktif menyembunyikan kunci tersebut; jangan taip kunci dalam arahan yang akan disimpan dalam sejarah terminal.

Untuk log masuk pelayar secara terus:

```sh
omi auth login --browser
```

Lakukan log masuk pada komputer yang sama di mana terminal berjalan, kerana pengesahan kembali ke alamat setempat. Ikuti arahan yang dipaparkan pada skrin.

Selepas itu, semak konfigurasi dan capaian API:

```sh
omi auth status
omi auth whoami
```

`status` menunjukkan keadaan setempat dan menyembunyikan rahsia, tetapi tidak mengesahkannya dengan pelayan. `whoami` menghantar permintaan yang disahkan; kejayaan bermakna kelayakan anda berfungsi dengan betul.

Konfigurasi disimpan secara lalai dalam `~/.omi/config.toml`. Jangan kongsi fail ini kerana ia mengandungi kelayakan peribadi anda.

## Lihat data anda

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Senarai kosong mungkin hanya bermakna tiada item yang sepadan dengan pertanyaan tersebut. Untuk mengetahui penapis sesuatu arahan, lihat bantuan:

```sh
omi memory list --help
omi action-item list --help
```

## Dapatkan JSON dan selak halaman

Letakkan pilihan global `--json` **sebelum** kumpulan arahan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Arahan pertama meminta 25 rekod pertama; arahan kedua meminta 25 rekod seterusnya. Oleh itu, satu halaman bukan sandaran penuh. Output JSON mengekalkan pengecam penuh, manakala paparan jadual mungkin memendekkannya.

Untuk menyimpan halaman ke dalam fail:

```sh
omi --json memory list --limit 25 --offset 0 > memori-halaman-1.json
```

Ubah hala ini mencipta atau menggantikan fail setempat. Sebelum menggunakan kandungannya, pastikan arahan berjaya dilaksanakan. Mesej ralat ditulis ke stderr; fail kosong bukan bukti ketiadaan data. Fail yang dieksport mungkin mengandungi maklumat peribadi: pastikan ia kekal sulit.

## Log keluar

```sh
omi auth logout
```

Arahan ini memadamkan kelayakan yang disimpan secara setempat. Untuk membatalkan kunci pada pelayan, gunakan pengurusan kunci pembangun dalam akaun anda.

Untuk arahan lain dan pilihan lanjutan, sila rujuk panduan utama dalam bahasa Inggeris:
[../README.md](../README.md) dan `omi --help`.
