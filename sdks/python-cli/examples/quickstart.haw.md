# ʻO nā hana mua me omi-cli

Hōʻike kēia alakaʻi i nā kauoha mua ma ka ʻōlelo Hawaiʻi. Noho mau nā inoa kauoha
a me nā memo o ka papahana ma ka ʻōlelo Pelekānia. ʻAʻole hoʻololi nā laʻana nīnau
i kāu mau hoʻomanaʻo, nā kamaʻilio, nā hana, a i ʻole nā pahuhopu.

## Hoʻokomo ʻana i ka papahana

Nā koina: Python 3.10 a i ʻole ʻoi aku ka hou a me kahi moʻokāki Omi.

Inā ua hoʻokomo ʻia ʻo `pipx`:

```sh
pipx install omi-cli
omi --help
```

Hiki nō ke hoʻokomo ma kahi kaʻe pūnaewele kūikawā (virtual environment) ma Python:

```sh
python -m pip install omi-cli
omi --help
```

Inā ʻaʻole loaʻa ʻo `omi` i ka puka kauoha (terminal), e hōʻoia e hana ana ke kaʻe
kūikawā a i ʻole aia ka waihona a `pipx` e waiho ai i nā faile ma kāu loli `PATH`.

## Hoʻohui i kāu moʻokāki

E hoʻomaka i ke kōkua hana kūkākūkā:

```sh
omi auth login
```

E koho e ʻeʻe ma o ka polokalamu kele pūnaewele (browser) a i ʻole e hoʻopili i kahi
kī API mea hoʻomohala Omi. Hūnā ka hoʻokomo pūnaewele i ke kī; mai kākau iā ia ma
kahi kauoha e waiho ʻia i loko o ka mōʻaukala o ka puka kauoha.

E hele pololei i ka polokalamu kele pūnaewele:

```sh
omi auth login --browser
```

E ʻeʻe ma ka lolouila like e holo nei ka puka kauoha: hoʻohana ka pane hōʻoia i kahi
helu wahi kūloko. E hahai i nā kuhikuhi ma ka pale.

Ma hope o kēlā, e hōʻoia i ka hoʻonohonoho a me ke komo ʻana i ka API:

```sh
omi auth status
omi auth whoami
```

Hōʻike ʻo `status` i ke kūlana kūloko a hūnā i ke kī malu, akā ʻaʻole nānā i ka mana
ma ke kikowaena pūnaewele. Hoʻouna ʻo `whoami` i kahi noi i hōʻoia ʻia; inā kūleʻa,
hōʻoia ia e hana ana nā ʻikepili me ka hōʻike ʻole ʻana i kou inoa.

Mālama paʻamau ʻia ka hoʻonohonoho ʻana ma `~/.omi/config.toml`. Mai kaʻana like i kēia
faile: aia paha kāu ʻike komo malu i loko.

## Nānā i kāu ʻikepili

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Hiki i kahi papa inoa hakahaka ke manaʻo wale ʻaʻohe mea e kūpono ana i ka nīnau.
E hoʻohana i ke kōkua e ʻike i nā kānana no kēlā me kēia kauoha:

```sh
omi memory list --help
omi action-item list --help
```

## Kiʻi ʻana iā JSON a me ka heluhelu ʻaoʻao ʻana

E hoʻonoho i ke koho laulā `--json` **ma mua** o ka pūʻulu kauoha:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Noi ke kauoha mua i nā hoʻomanaʻo 25 mua; noi ka lua i nā 25 aʻe. No laila, ʻaʻole
kahi ʻaoʻao he kope mālama piha (backup). Mālama ka hoʻopuka JSON i nā ID piha,
ʻoiai hiki i nā papa ma ka pale ke hoʻopōkole iā lākou.

E mālama i kahi ʻaoʻao ma kahi faile:

```sh
omi --json memory list --limit 25 --offset 0 > hoomanao-aoao-1.json
```

Hana a hoʻololi paha kēia hoʻohuli ʻana i ka faile kūloko. E hōʻoia ua pau ke kauoha
me ka hewa ʻole ma mua o ka hoʻohana ʻana i ka ʻike. Kākau ʻia nā hewa i ke kahawai
hewa (stderr); ʻaʻole hōʻoia ka faile hakahaka ʻaʻohe ʻikepili. Hiki i ka faile ke
loaʻa ka ʻike pilikino: e mālama malu iā ia.

## Haʻalele (Logout)

```sh
omi auth logout
```

Holoi kēia kauoha i nā hōʻoia i mālama ʻia ma kahi kūloko. No ka hoʻopau ʻana i kahi
kī ma ke kikowaena, e hoʻohana i ka hoʻokele kī mea hoʻomohala ma kāu moʻokāki.

No nā kauoha ʻē aʻe a me nā koho hou aku, e ʻike i
[ke alakaʻi kumu ma ka ʻōlelo Pelekānia](../README.md) a me `omi --help`.
