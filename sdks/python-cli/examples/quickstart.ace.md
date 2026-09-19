# Phôn Bagah ngön omi-cli

Buku pandoman nyoë geupeujeulaih peurintah-peurintah dasa lam Bahsa Acèh. Nan peurintah ngön peusan nibak program teutap geungui Bahsa Inggrèh. Conto parèksa (query) di yup nyoë hântom geuöbah ingatan (memories), haba mariet (conversations), buet (action items), atawa tujuën (goals) droeneuh.

## Pasang program

Syarat: Python 3.10 atawa vèrsi nyang léubèh barô seureuta akun Omi.

Meunyoë droeneuh ka geupasang `pipx`:

```sh
pipx install omi-cli
omi --help
```

Seubagoe peuniléh laén, droeneuh jeuet geupasang lam lingkungan virtual Python nyang teungoh aktip:

```sh
python -m pip install omi-cli
omi --help
```

Meunyoë terminal hân meuteumèe `omi`, peupaseuti lingkungan virtual ka aktip atawa folder èksekusi nibak `pipx` ka na lam `$PATH` droeneuh.

## Peuhubong akun droeneuh

Jalankan asisten interaktip:

```sh
omi auth login
```

Péléh tamöng rot browser atawa tèmpèl kunci API peugot Omi. Input interaktip jiseubôk kunci; bèk tuléh kunci lam peurintah nyang teumpat meusimpan lam riwayat terminal.

Mangat lêngsong ngön browser:

```sh
omi auth login --browser
```

Tamöng bak komputer nyang saban ngön teumpat terminal geupajalan: jaweuëb auténtikasi geungui alamat lokal. Seutöt peunutôh bak laya.

‘Oh lheueh nyan, parèksa konfigurasi ngön aksès API:

```sh
omi auth status
omi auth whoami
```

`status` geupeuleumah keuadaan lokal ngön jiseubôk rahsia, tapi hân jiparèksa keusahan bak server. `whoami` geukirém peumakri nyang ka geu-auténtikasi; meunyoë meuhasél, nyoë geupeunyata kredensial mubuet ngön gèt tan payah peuleumah nan droeneuh.

Meunurôt adat konfigurasi teusimpan bak `~/.omi/config.toml`. Bèk bago berkas nyoë saweueb jeuet na asoe kredensial rahsia droeneuh.

## Parèksa data droeneuh

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Dapeuta nyang soh jeuet mantong meuma'na tan barang nyang meucocok ngön peunyareng. Ngui beunantu mangat teupeue peunyareng bak tiêp peurintah:

```sh
omi memory list --help
omi action-item list --help
```

## Cok JSON ngön pinda on (Pagination)

Keubah peuniléh global `--json` **yoh goh** kawan peurintah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Peurintah phôn meulakèe 25 ingatan phôn; peurintah keudua, 25 dudoe teuma. Sa-on kon cadangan nyang peunoh. Hasél JSON teutap meukukôh identifier peunoh, seumentara tabel bak laya jeuet geupeupadék mangat gèt leumah.

Mangat keubah sa-on lam saboh berkas:

```sh
omi --json memory list --limit 25 --offset 0 > ingatan-on-1.json
```

Peunindaan nyoë geupeugot atawa geuganto berkas lokal. Peupaseuti peurintah ka reuda ngön sampôrna yoh goh geungui asoeneuh. Keusalahan geutuléh bak teumpat teubiet salah (stderr); berkas nyang soh kon jaminan tan data. Berkas nyang ka geu-èkspor jeuet na asoe haba pribadi: simpan ngön aman.

## Teubiet nibak akun (Logout)

```sh
omi auth logout
```

Peurintah nyoë geusampôh kredensial nyang teusimpan bak lokal. Mangat batay kunci bak server, ngui atoran kunci peugot bak akun droeneuh.

Keu peurintah laén ngön peuniléh nyang léubèh leubèh, kalon [buku pandoman utama lam Bahsa Inggrèh](../README.md) seureuta `omi --help`.
