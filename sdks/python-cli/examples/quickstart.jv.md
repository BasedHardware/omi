# Quickstart CLI Omi (Basa Jawa)

Pandhuan iki bakal mbantu sampeyan miwiti nggunakake antarmuka baris prentah (`omi` CLI).

Kanggo dokumentasi paling anyar lan komprehensif, mangga deleng [README Utama basa Inggris](../README.md).

## Prasyarat

- Python 3.10 utawa luwih anyar
- Akun Omi (mangga mlebu liwat aplikasi seluler utawa web dhisik)

## Masang CLI (Installation)

Cara paling gampang yaiku masang nganggo [pipx](https://github.com/pypa/pipx) supaya lingkungane terisolasi:

```sh
pipx install omi-cli
```

Utawa nggunakake `pip` ing lingkungan virtual (venv):

```sh
python -m venv .venv
source .venv/bin/activate  # Ing Windows: .venv\Scripts\activate
pip install omi-cli
```

> **Cathetan:** Jeneng paket PyPI yaiku `omi-cli`, nanging prentah sing dienggo ing terminal yaiku `omi`.

## Otentikasi (Mlebu Akun)

Sadurunge nggunakake prentah liyane, sampeyan kudu mlebu menyang akun Omi dhisik:

```sh
omi auth login
```

Prentah iki bakal mbukak browser kanggo proses mlebu akun. Sawise sukses, token otentikasi bakal kasimpen kanthi aman ing komputer sampeyan.

Yen sampeyan nggunakake lingkungan tanpa layar (headless/server) utawa CI/CD, sampeyan bisa nggunakake kunci API kanthi nyetel variabel lingkungan:

```sh
export OMI_API_KEY="kunci-api-sampeyan"
```

Utawa nganggo pilihan `--api-key`:

```sh
omi --api-key "kunci-api-sampeyan" memory list
```

## Prentah Dhasar

### Ndeleng Memori (Memories)

Ndeleng dhaptar memori paling anyar:

```sh
omi memory list
```

Ndeleng rincian memori tartamtu adhedhasar ID:

```sh
omi memory get <memory-id>
```

### Nggoleki Memori

Nggoleki memori adhedhasar tembung kunci tartamtu:

```sh
omi memory search "rapat proyek wingi"
```

### Informasi Pangguna

Ndeleng profil pangguna sing lagi aktif:

```sh
omi auth status
```

Metu saka akun (logout):

```sh
omi auth logout
```

## Format Metu JSON

Kabeh prentah ndhukung pilihan `--json` kanggo ngasilake data kanthi format JSON sing gampang diolah nganggo skrip utawa piranti kaya `jq`:

```sh
# Pilihan global dilebokake sadurunge subprentah:
omi --json memory list | jq '.[0].structured.title'
```

## Profil Pangguna (Profiles)

Yen nggunakake sawetara akun utawa lingkungan sing beda, gunakake pilihan `--profile` (utawa `-p`):

```sh
omi --profile work auth login
omi --profile work memory list
```

Yen ora ditemtokake, sistem bakal nggunakake profil saka variabel lingkungan `OMI_PROFILE` dhisik, banjur nggunakake profil aktif saka berkas konfigurasi (standare yaiku `default`). Kabeh profil kasimpen ing `~/.omi/config.toml`.

## Kode Metu (Exit Codes)

Kanggo skrip lan otomatisasi, CLI nemtokake kode metu sing cetha:

| Kode | Tegese | Katrangan |
| :---: | :--- | :--- |
| `0` | Sukses | Prentah wis rampung kaleksanan kanthi bener. |
| `1` | Kaluputan Panggunaan | Kaluputan sintaksis, pilihan ora dingerteni, argumen kurang, utawa nggabungake pilihan sing ora cocog. |
| `2` | Kaluputan Otentikasi | Ora ana kredensial, token wis kadaluwarsa, utawa hak akses kurang. |
| `3` | Kaluputan Server | Tanggapan 5xx, sambungan gagal, utawa ana masalah jaringan. |
| `4` | Watesan Panjaluk (Rate Limited) | 429 Too Many Requests. |
| `5` | Ora Ditemokake | 404 Not Found (ID sing dijaluk ora ana). |

Kode `4` biasane mung sauntara — enteni sedhela banjur coba maneh. CLI bakal nyoba maneh panjaluk sing kena watesan (429) kanthi otomatis, lan manut marang instruksi `Retry-After` saka server. Kode `3` biasane mung sauntara kanggo maca data, nanging kanggo prentah nulis data bisa uga ateges asile durung mesthi (`outcome unknown`) — server bisa uga wis ngetrapake owah-owahan kasebut. Priksa sumber daya sadurunge nyoba maneh. Kode `2` tegese masalah otentikasi (ora ana kredensial utawa token kadaluwarsa), lakokake `omi auth login` maneh. Kode `1` tegese kaluputan argumen utawa panggunaan prentah, benerake pilihan sing diketik. Kode `5` ateges ID sing dijaluk pancen ora ana utawa ora bisa diakses.

Kanggo prentah liyane lan setelan luwih jangkep, waca [README Utama basa Inggris](../README.md) lan `omi --help`.
