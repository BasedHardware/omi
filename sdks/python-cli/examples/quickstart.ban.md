# Langkah kapertama sareng omi-cli

Piteket puniki ngeninin indik langkah kapertama nganggén omi-cli ring basa Bali. Parinama perintah miwah pesen program tetep ring basa Inggris. Conto-conto ring piteket puniki nenten ngubah memori, obrolan, item aksi, utawi tatujon ragané.

## Ngelukar

Ragané perlu Python 3.10 utawi sané anyar, miwah akun Omi.

Yéning `pipx` sampun kaukur:

```sh
pipx install omi-cli
omi --help
```

Yéning nénten, ukur ring lingkungan virtual Python sané aktif:

```sh
python -m pip install omi-cli
omi --help
```

Yéning terminal nénten manggihin `omi`, cek indik lingkungan virtual aktif utawi direktori pipx wenten ring `$PATH`.

## Nyambungaké akun

Ngawitin wizard login interaktif:

```sh
omi auth login
```

Ragané prasida milih login nganggén browser utawi ngenahang kunci API pangembang Omi. Login interaktif nyamunikai kunci ragané; ati-ati mangda nénten kantun ring sejarah terminal.

Kéngkén login langsung nganggén browser:

```sh
omi auth login --browser
```

Login ring komputer sané sami sareng terminal: wangsulan otorisasi nganggén alamat lokal. Teterin pituduh ring layar.

Cek konfigurasi miwah kunci API mangkin:

```sh
omi auth status
omi auth whoami
```

`status` ngenahang status lokal miwah nyamunikai rahasia, nanging nénten macek sareng server. `whoami` ngaryanin panyuwunan sané kawenang; yéning sukses, ngenegtegang otorisasi ragané karya, nanging nénten ngenahang wastan ragané.

Konfigurasi wenten ring `~/.omi/config.toml`. Eda ngabagi berkas puniki: prasida ngisi rahasia login.

## Nylinguk data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lis sané kosong prasida maartos nénten wenten data sané cocog. Mempelajari filter tiap perintah, cingak bantuan:

```sh
omi memory list --help
omi action-item list --help
```

## Keluaran JSON miwah paginasi

Genahang opsi global `--json` **sadurung** kelompok perintah:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Perintah kapertama mendet 25 memori kapertama; sane kaping kalih mendet 25 salanturné. Asiki kaca sering nénten kebak. Keluaran JSON nyimpen makasami identifier, nanging tabel ring layar sering motong.

Kéngkén nyurat kaca nuju berkas:

```sh
omi --json memory list --limit 25 --offset 0 > memori-kaca-1.json
```

Pangalihan ngaryanin utawi nyurat berkas lokal. Cek perintah sukses sadurung nganggén isiné. Kesalahan nuju stderr; berkas kosong nénten maartos nénten wenten data. Berkas sané kapolihang prasida ngisi informasi pribadi: simpen antuk aman.

## Medal

```sh
omi auth logout
```

Perintah puniki ngicalang otorisasi lokal sané kasimpen. Kéngkén nyabut kunci ring server, nganggén pangaturan kunci pangembang ring akun ragané.

Kéngkén perintah tiosan miwah opsi lanjutan, cingak [Piteket ageng basa Inggris](../README.md) miwah `omi --help`.
