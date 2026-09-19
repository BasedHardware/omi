# Mimiti Gancang ngagunakeun omi-cli

Pituduh ieu ngécéskeun paréntah-paréntah dasar dina basa Sunda (Basa Sunda). Ngaran paréntah sareng pesen ti program tetep ngagunakeun basa Inggris. Conto pamariksaan (query) di handap henteu ngarobih memori, obrolan, pancén (action items), atanapi udagan (goals) anjeun.

## Masang program

Sarat: Python 3.10 atanapi vérsi anu langkung énggal sareng akun Omi.

Upami anjeun parantos masang `pipx`:

```sh
pipx install omi-cli
omi --help
```

Salaku alternatif, anjeun tiasa masang dina lingkungan virtual Python anu aktip:

```sh
python -m pip install omi-cli
omi --help
```

Upami terminal henteu mendakan `omi`, pastikeun lingkungan virtual parantos aktip atanapi folder éksekusi tina `pipx` aya dina `$PATH` anjeun.

## Nyambungkeun akun anjeun

Jalankeun asistén interaktif:

```sh
omi auth login
```

Pilih asup liwat browser atanapi témpélkeun konci API pamekar Omi. Input interaktif nyumputkeun konci; ulah nyerat konci dina paréntah anu bakal kacatet dina sajarah terminal.

Pikeun langsung ngagunakeun browser:

```sh
omi auth login --browser
```

Asup dina komputer anu sami sareng tempat terminal dijalankeun: réspon auténtikasi ngagunakeun alamat lokal. Turutan pituduh dina layar.

Saatos éta, parios konfigurasi sareng aksés API:

```sh
omi auth status
omi auth whoami
```

`status` nembongkeun kaayaan lokal sareng nyumputkeun rusiah, tapi henteu mariksa validitasna di sérver. `whoami` ngirim pamundut anu parantos diauténtikasi; upami hasil, ieu ngabuktikeun yén kredénsial tiasa dianggo tanpa kedah nembongkeun nami anjeun.

Sacara standar konfigurasi disimpen dina `~/.omi/config.toml`. Ulah bagikeun berkas ieu kusabab tiasa ngandung kredénsial rusiah anjeun.

## Mariksa data anjeun

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Daptar anu kosong tiasa waé hartosna teu aya barang anu cocog sareng panyaring. Anggo bantosan pikeun mendakan panyaring dina unggal paréntah:

```sh
omi memory list --help
omi action-item list --help
```

## Meunangkeun JSON sareng napigasi kaca (Pagination)

Tunda pilihan global `--json` **sateuacan** grup paréntah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Paréntah kahiji mundut 25 memori awal; paréntah kadua, 25 salajengna. Sakaca sanés cadangan anu lengkep. Kaluaran JSON nahan identifier lengkep, sedengkeun tabél dina layar tiasa pondok pikeun ditingalikeun.

Pikeun nyimpen sakaca kana hiji berkas:

```sh
omi --json memory list --limit 25 --offset 0 > memori-kaca-1.json
```

Parobihan ieu nyiptakeun atanapi ngagentos berkas lokal. Pastikeun paréntah parantos réngsé sacara sampurna sateuacan ngagunakeun eusina. Kasalahan diserat kana output kasalahan (stderr); berkas anu kosong sanés jaminan yén teu aya data. Berkas anu diékspor tiasa ngandung inpormasi pribadi: simpen kalayan aman.

## Kaluar tina akun (Logout)

```sh
omi auth logout
```

Paréntah ieu ngahapus kredénsial anu disimpen sacara lokal. Pikeun ngabatalkeun konci di sérver, anggo pangaturan konci pamekar dina akun anjeun.

Pikeun paréntah sanés sareng pilihan langkung lengkep, tingal [pituduh utama dina basa Inggris](../README.md) sareng `omi --help`.
