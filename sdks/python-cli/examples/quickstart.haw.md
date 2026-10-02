# Nā hana mua me omi-cli

Ke wehewehe nei kēia alakaʻi i nā kauoha mua (commands) o ka omi-cli ma ka ʻōlelo Hawaiʻi. E noho mau ana nā inoa kauoha a me nā leka o ka polokalamu ma ka ʻōlelo Pelekania. ʻAʻole e hoʻololi nā laʻana huli i hōʻike ʻia ma ʻaneʻi i kāu mau hoʻomanaʻo (memories), kāu mau kamaʻilio (conversations), kāu mau hana (action items), a i ʻole kāu mau pahuhopu (goals).

## Hoʻokomo

Pono: Python 3.10 a ʻoi aku paha, a me kahi moʻokāki Omi.

Inā loaʻa iā ʻoe ka `pipx`:

```sh
pipx install omi-cli
omi --help
```

Hiki nō hoʻi iā ʻoe ke hoʻokomo i loko o kahi kaiapuni Python hana:

```sh
python -m pip install omi-cli
omi --help
```

Inā ʻaʻole ʻike ka terminal iā `omi`, e hōʻoiaʻiʻo ua hana ke kaiapuni a i ʻole aia ka waihona `pipx` ma `$PATH`.

## Hoʻohui i kāu moʻokāki

E hoʻomaka i ke kōkua pili:

```sh
omi auth login
```

E koho i ke komo ʻana ma ka polokalamu kele a i ʻole ke kau ʻana i kahi kī API o Omi developer. Hūnā ke komo pili i ke kī; pale i ke kākau ʻana iā ia i loko o kahi kauoha e mālama ʻia ana ma ka moʻolelo terminal.

No ka hele pololei i ka polokalamu kele:

```sh
omi auth login --browser
```

E komo ma ka lolouila hoʻokahi me ka terminal: hele ke pane hōʻoia i ka wāhi kūloko. E hahai i nā kuhikuhi ma ka pale.

Ma hope, e hōʻoia i ka hoʻonohonoho a me ke komo API:

```sh
omi auth status
omi auth whoami
```

Hōʻike ka `status` i ke kūlana kūloko a hūnā i ka mea huna, akā ʻaʻole ia e hōʻoia i ka pono ma ka server. Hana ka `whoami` i kahi noi hōʻoia; inā holomua, maopopo e hana ana nā ʻikepili komo, me ka hōʻike ʻole i kou inoa.

Mālama ʻia ka hoʻonohonoho ma ke ʻano maʻamau ma `~/.omi/config.toml`. Mai kaʻana like i kēia faila: hiki ke loaʻa nā ʻikepili komo huna.

## Nānā i kāu ʻikepili

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ʻO ka papa inoa ʻole maʻamau he mea ʻole i kūlike me ka huli. E hoʻohana i ke kōkua no ka ʻimi ʻana i nā kānana o kēlā me kēia kauoha:

```sh
omi memory list --help
omi action-item list --help
```

## JSON a me nā ʻaoʻao

E kau i ke koho honua `--json` **ma mua** o ka pūʻulu kauoha:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Noi ke kauoha mua i nā hoʻomanaʻo 25 mua; noi ka lua i nā 25 aʻe. ʻAʻole kope piha hoʻokahi ʻaoʻao. Mālama ka JSON i nā helu holoʻokoʻa, akā hiki i nā pākaukau ma ka pale ke pōkole iā lākou.

No ka mālama ʻana i kahi ʻaoʻao i loko o kahi faila:

```sh
omi --json memory list --limit 25 --offset 0 > hoʻomanaʻo-ʻaoʻao-1.json
```

Hana a kākau hou kēia hoʻohuli i kahi faila kūloko. E hōʻoiaʻiʻo ua pau ke kauoha ma mua o kou hoʻohana ʻana i ka ʻike. Kākau ʻia nā hewa i ka pane hewa (stderr); ʻaʻole hōʻoia kahi faila ʻole i ka ʻole o ka ʻikepili. Hiki ke loaʻa ka ʻike pilikino i kahi faila i hoʻokuʻu ʻia: mālama huna.

## Puka aku

```sh
omi auth logout
```

Holoi kēia kauoha i nā ʻikepili komo i mālama ʻia kūloko. No ka hoʻopau ʻana i kahi kī ma ka server, e hoʻohana i ka hoʻokele kī developer ma kāu moʻokāki ponoʻī.

No nā kauoha a me nā koho hou aʻe, e nānā i ke [alakaʻi nui ma ka ʻōlelo Pelekania](../README.md) a me `omi --help`.
