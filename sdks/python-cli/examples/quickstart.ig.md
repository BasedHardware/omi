# Ibido na omi-cli

Ntuziaka a na-egosi iwu ole na ole mbụ n'asụsụ Igbo. Aha iwu na ozi usoro na-anọgide n'asụsụ Bekee. Ihe atụ ọgụgụ e nyere ebe a agaghị agbanwe ncheta, mkparịta ụka, ndepụta ọrụ ma ọ bụ ebumnuche gị.

## Wụnye ngwanrọ

Ihe achọrọ: Python 3.10 ma ọ bụ nke kachasị ọhụrụ yana akaụntụ Omi.

> Rịba ama: Aha ngwugwu na PyPI bụ **`omi-cli`**, ebe iwu na-agba ọsọ mgbe echichi gasịrị bụ **`omi`**. Enwere ngwugwu dị iche na-enweghị njikọ akpọrọ `omi` na PyPI — awụnyela ngwugwu ahụ.

Ọ bụrụ na arụnyere `pipx`:

```sh
pipx install omi-cli
omi --help
```

N'aka nke ọzọ, n'ime gburugburu mebere Python na-arụ ọrụ:

```sh
python -m pip install omi-cli
omi --help
```

Ọ bụrụ na ọnụ na-agụghị `omi`, lelee na gburugburu mebere na-arụ ọrụ ma ọ bụ na ndekọ `pipx` dị na `PATH` gị.

## Jikọọ akaụntụ gị

Malite onye inyeaka mmekọrịta:

```sh
omi auth login
```

Họrọ ịbanye site na ihe nchọgharị, ma ọ bụ họrọ nhọrọ mado igodo API onye nrụpụta Omi. Ntinye mmekọrịta na-ezochi igodo ahụ; atụnyela igodo n'iwu ga-anọ na akụkọ ihe mere eme ọnụ.

Maka nbanye ihe nchọgharị ozugbo:

```sh
omi auth login --browser
```

Mee nbanye na otu kọmputa ebe ọnụ na-agba ọsọ, n'ihi na nkwenye na-alaghachi na adreesị mpaghara. Soro ntuziaka na-egosi na ihuenyo.

Mgbe nke ahụ gasịrị, lelee nhazi na ohere API:

```sh
omi auth status
omi auth whoami
```

`status` na-egosi ọnọdụ mpaghara ma na-ezochi nzuzo, mana anaghị enyocha ya na sava ahụ. `whoami` na-eziga arịrịọ enyere ikike; ihe ịga nke ọma pụtara na nzere na-arụ ọrụ nke ọma.

A na-echekwa nhazi na ndabara na `~/.omi/config.toml`. Ekekwala faịlụ a n'ihi na o nwere nzere nkeonwe gị.

## Lelee data gị

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ndepụta efu nwere ike ịpụta na ọ nweghị ihe dabara na ajụjụ ahụ. Iji ghọta ihe nzacha nke iwu, lee enyemaka:

```sh
omi memory list --help
omi action-item list --help
```

## Nweta JSON ma gbanwee ibe

Tinye nhọrọ zuru ụwa ọnụ `--json` **tupu** otu iwu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Iwu mbụ na-arịọ ndekọ 25 mbụ; nke abụọ na-arịọ 25 ọzọ. Ya mere otu ibe abụghị nkwado zuru ezu. Mmepụta JSON na-ejigide njirimara zuru oke, ebe tebụl nwere ike imechi ha.

Iji chekwaa ibe na faịlụ:

```sh
omi --json memory list --limit 25 --offset 0 > ncheta-ibe-1.json
```

Ntugharị a na-emepụta ma ọ bụ na-anọchi faịlụ mpaghara. Tupu iji ọdịnaya, hụ na iwu ahụ gara nke ọma. A na-ede mperi na stderr; faịlụ efu abụghị ihe akaebe na ọ nweghị data. Faịlụ echekwara nwere ike ịnwe ozi nkeonwe: debe ya na nzuzo.

## Pụọ (Log out)

```sh
omi auth logout
```

Iwu a na-ewepụ nzere echekwara na mpaghara. Iji kagbuo igodo na sava ahụ, jiri njikwa igodo onye nrụpụta na akaụntụ gị.

Maka iwu ndị ọzọ na nhọrọ dị elu, biko hụ isi ntuziaka Bekee:
[../README.md](../README.md) na `omi --help`.
