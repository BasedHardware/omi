# Ka hoʻomaka ʻana me omi-cli

Hōʻike kēia alakaʻi i nā kauoha mua ma ka ʻōlelo Hawaiʻi. Noho mau nā inoa kauoha a me nā memo ʻōnaehana ma ka ʻōlelo Pelekania. ʻAʻole e hoʻololi nā hiʻohiʻona heluhelu i hāʻawi ʻia ma ʻaneʻi i kāu mau hoʻomanaʻo, nā kamaʻilio, nā papa hana, a i ʻole nā pahuhopu.

## E hoʻouka i ka polokalamu

Nā Koina: Python 3.10 a i ʻole ka mana hou a me kahi moʻokāki Omi.

> Nānā: ʻO ka inoa o ka pūʻolo ma PyPI ʻo **`omi-cli`**, ʻoiai ʻo ke kauoha e holo ana ma hope o ka hoʻokomo ʻana ʻo **`omi`**. Aia kekahi pūʻolo ʻokoʻa i pili ʻole i kapa ʻia ʻo `omi` ma PyPI — mai hoʻokomo i kēlā pūʻolo.

Inā ua hoʻokomo ʻia ʻo `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ma kahi ʻē aʻe, i loko o kahi kaiapuni uila Python e hana ana:

```sh
python -m pip install omi-cli
omi --help
```

Inā ʻaʻole loaʻa iā ʻoe ʻo `omi`, e hōʻoia i ka hana ʻana o ke kaiapuni uila a i ʻole aia ka papa kuhikuhi `pipx` i kāu `PATH`.

## E hoʻohui i kāu moʻokāki

E hoʻomaka i ke kōkua pili:

```sh
omi auth login
```

E koho e komo ma o ka polokalamu kele pūnaewele, a i ʻole e koho i ke koho e hoʻopili i ke kī API mea hoʻomohala Omi. Hūnā ka hoʻokomo ʻana i ke kī; mai kākau i ke kī i nā kauoha e mālama ʻia ma ka moʻolelo pahu hopu.

No ke komo pololei ʻana ma o ka polokalamu kele:

```sh
omi auth login --browser
```

E hoʻopau i ke komo ʻana ma ka lolouila like e holo nei i ka pahu hopu, no ka mea e hoʻi mai ka hōʻoia ʻana i kahi helu wahi kūloko. E hahai i nā kuhikuhi ma ka pale.

Ma hope o kēlā, e nānā i ka hoʻonohonoho a me ke komo ʻana i ka API:

```sh
omi auth status
omi auth whoami
```

Hōʻike ʻo `status` i ke kūlana kūloko a hūnā i nā mea huna, akā ʻaʻole ia e hōʻoia me ke kikowaena. Hoʻouna ʻo `whoami` i kahi noi ʻae ʻia; ʻo ka lanakila ʻana he manaʻo e hana pono ana kāu mau hōʻoia.

Mālama ʻia ka hoʻonohonoho ʻana ma `~/.omi/config.toml`. Mai kaʻana like i kēia faila no ka mea aia kāu mau ʻike pilikino.

## E nānā i kāu ʻikepili

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Hiki i kahi papa inoa kaʻawale ke ʻano ʻaʻohe mea i kūlike me kāu noi. No ka ʻike ʻana i nā kānana o kekahi kauoha, e nānā i ke kōkua:

```sh
omi memory list --help
omi action-item list --help
```

## E kiʻi i ka JSON a me ka huli ʻaoʻao

E kau i ke koho laulā `--json` **ma mua** o ka pūʻulu kauoha:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Noi ke kauoha mua i nā moʻolelo he 25 mua; noi ka lua i nā 25 aʻe. No laila, ʻaʻole he kope piha kahi ʻaoʻao hoʻokahi. Mālama ka hopena JSON i nā mea hōʻike piha, ʻoiai e hoʻopōkole paha nā papa kuhikuhi iā lākou.

E mālama i kekahi ʻaoʻao ma kahi faila:

```sh
omi --json memory list --limit 25 --offset 0 > hoomanao-aoao-1.json
```

Hana a hoʻololi paha kēia hoʻohuli hou i kahi faila kūloko. Ma mua o ka hoʻohana ʻana i ka ʻike, e hōʻoia ua holomua ke kauoha. Kākau ʻia nā hemahema ma stderr; ʻaʻole hōʻoia kahi faila kaʻawale i ka loaʻa ʻole o ka ʻikepili. E mālama pono i kēia faila no ka mea he ʻike pilikino paha kona.

## E puka i waho (Log out)

```sh
omi auth logout
```

Wehe kēia kauoha i nā hōʻoia i mālama ʻia ma kahi kūloko. E kāpae a hoʻopau paha i kahi kī ma ke kikowaena, e hoʻohana i ka hoʻokele kī mea hoʻomohala ma kāu moʻokāki.

No nā kauoha ʻē aʻe a me nā koho holomua, e ʻoluʻolu e nānā i ke alakaʻi kumu ma ka ʻōlelo Pelekania:
[../README.md](../README.md) a me `omi --help`.
