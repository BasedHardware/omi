# Ph\u00f4n Bagah ng\u00f6n omi-cli

Buku pandoman nyo\u00eb geupeujeulaih peurintah-peurintah dasa lam Bahsa Ac\u00e8h. Nan peurintah ng\u00f6n peusan nibak program teutap geungui Bahsa Inggr\u00e8h. Conto par\u00e8ksa (query) di yup nyo\u00eb h\u00e2ntom geu\u00f6bah ingatan (memories), haba mariet (conversations), buet (action items), atawa tuju\u00ebn (goals) droeneuh.

## Pasang program

Syarat: Python 3.10 atawa v\u00e8rsi nyang l\u00e9ub\u00e8h bar\u00f4 seureuta akun Omi.

Meunyo\u00eb droeneuh ka geupasang `pipx`:

```sh
pipx install omi-cli
omi --help
```

Seubagoe peunil\u00e9h la\u00e9n, droeneuh jeuet geupasang lam lingkungan virtual Python nyang teungoh aktip:

```sh
python -m pip install omi-cli
omi --help
```

Meunyo\u00eb terminal h\u00e2n meuteum\u00e8e `omi`, peupaseuti lingkungan virtual ka aktip atawa folder \u00e8ksekusi nibak `pipx` ka na lam `$PATH` droeneuh.

## Peuhubong akun droeneuh

Jalankan asisten interaktip:

```sh
omi auth login
```

P\u00e9l\u00e9h tam\u00f6ng rot browser atawa t\u00e8mp\u00e8l kunci API peugot Omi. Input interaktip jiseub\u00f4k kunci; b\u00e8k tul\u00e9h kunci lam peurintah nyang teumpat meusimpan lam riwayat terminal.

Mangat l\u00eangsong ng\u00f6n browser:

```sh
omi auth login --browser
```

Tam\u00f6ng bak komputer nyang saban ng\u00f6n teumpat terminal geupajalan: jaweu\u00ebb auténtikasi geungui alamat lokal. Seut\u00f6t peunut\u00f4h bak laya.

‘Oh lheueh nyan, par\u00e8ksa konfigurasi ng\u00f6n aks\u00e8s API:

```sh
omi auth status
omi auth whoami
```

`status` geupeuleumah keuadaan lokal ng\u00f6n jiseub\u00f4k rahsia, tapi h\u00e2n jipar\u00e8ksa keusahan bak server. `whoami` geukir\u00e9m peumakri nyang ka geu-auténtikasi; meunyo\u00eb meuhas\u00e9l, nyo\u00eb geupeunyata kredensial mubuet ng\u00f6n g\u00e8t tan payah peuleumah nan droeneuh.

Meunur\u00f4t adat konfigurasi teusimpan bak `~/.omi/config.toml`. B\u00e8k bago berkas nyo\u00eb saweueb jeuet na asoe kredensial rahsia droeneuh.

## Par\u00e8ksa data droeneuh

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Dapeuta nyang soh jeuet mantong meuma'na tan barang nyang meucocok ng\u00f6n peunyareng. Ngui beunantu mangat teupeue peunyareng bak ti\u00eap peurintah:

```sh
omi memory list --help
omi action-item list --help
```

## Cok JSON ng\u00f6n pinda on (Pagination)

Keubah peunil\u00e9h global `--json` **yoh goh** kawan peurintah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Peurintah ph\u00f4n meulak\u00e8e 25 ingatan ph\u00f4n; peurintah keudua, 25 dudoe teuma. Sa-on kon cadangan nyang peunoh. Has\u00e9l JSON teutap meukuk\u00f4h identifier peunoh, seumentara tabel bak laya jeuet geupeupad\u00e9k mangat g\u00e8t leumah.

Mangat keubah sa-on lam saboh berkas:

```sh
omi --json memory list --limit 25 --offset 0 > ingatan-on-1.json
```

Peunindaan nyo\u00eb geupeugot atawa geuganto berkas lokal. Peupaseuti peurintah ka reuda ng\u00f6n samp\u00f4rna yoh goh geungui asoeneuh. Keusalahan geutul\u00e9h bak teumpat teubiet salah (stderr); berkas nyang soh kon jaminan tan data. Berkas nyang ka geu-\u00e8kspor jeuet na asoe haba pribadi: simpan ng\u00f6n aman.

## Teubiet nibak akun (Logout)

```sh
omi auth logout
```

Peurintah nyo\u00eb geusamp\u00f4h kredensial nyang teusimpan bak lokal. Mangat batay kunci bak server, ngui atoran kunci peugot bak akun droeneuh.

Keu peurintah la\u00e9n ng\u00f6n peunil\u00e9h nyang l\u00e9ub\u00e8h leub\u00e8h, kalon [buku pandoman utama lam Bahsa Inggr\u00e8h](../README.md) seureuta `omi --help`.
