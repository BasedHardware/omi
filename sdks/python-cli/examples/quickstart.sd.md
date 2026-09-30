# omi-cli لاءِ سنڌي تڪڙو آغاز

هي رهنمائي سنڌي ڳالهائيندڙن کي ٽرمينل مان Omi استعمال ڪرڻ جا پهريان قدم
ڏيکاري ٿي. ڪمانڊن، اختيارن ۽ پروگرام جي پيغامن جا نالا انگريزي ۾ ئي رهندا.
هيٺ ڏنل پڙهڻ وارا مثال توهان جي يادگيرين، ڳالهين، ڪمن يا مقصدن ۾ ڪا تبديلي
نه ٿا آڻين.

## انسٽال ڪرڻ

گهربل شيون: Python 3.10 يا ان کان نئون ۽ Omi کاتو.

الڳ ۽ صاف انسٽاليشن لاءِ `pipx` تجويز ڪجي ٿي:

```sh
pipx install omi-cli
omi --help
```

يا فعال Python virtual environment ۾ انسٽال ڪريو:

```sh
python -m pip install omi-cli
omi --help
```

PyPI پيڪيج جو نالو `omi-cli` آهي، پر ٽرمينل ڪمانڊ `omi` آهي. جيڪڏهن ٽرمينل
`omi` نه ڳولي، ته virtual environment فعال ڪريو يا `pipx` جي executable
directory کي پنهنجي `PATH` ۾ شامل ڪريو.

## کاتي سان ڳنڍڻ

بغير اختيار جي interactive لاگ اِن شروع ڪريو:

```sh
omi auth login
```

پروگرام browser (Google يا Apple) يا developer API key جو انتخاب ڏيکاريندو.
ڪمانڊ ۾ key لکڻ بدران لڪل interactive prompt استعمال ڪريو، جيئن key shell
history ۾ محفوظ نه ٿئي.

صرف browser وارو رستو هلائڻ لاءِ:

```sh
omi auth login --browser
```

Developer key لاءِ [app.omi.me](https://app.omi.me) ۾ Developer → API Keys
مان key وٺي هي ڪمانڊ هلائو:

```sh
omi auth login --api-key omi_dev_...
```

CI يا عارضي agent session ۾ key ماحول جي variable ۾ رکڻ وڌيڪ مناسب آهي:

```sh
export OMI_API_KEY="omi_dev_your_key_here"
```

`OMI_API_KEY` تڏهن استعمال ٿئي ٿي جڏهن موجوده profile ۾ key محفوظ نه هجي؛ محفوظ
profile key کي ترجيح حاصل آهي.

لاگ اِن جي ٻن مختلف جانچن کي نه ملايو:

```sh
omi auth status
omi auth whoami
```

`status` مقامي profile، masked credential ۽ expiry ڏيکاري ٿي ۽ network کانسواءِ
هلندي آهي. `whoami` Omi server کي authenticated درخواست موڪلي key جي حقيقي
صحت جانچي ٿي.

`auth refresh` صرف browser/OAuth profile لاءِ آهي؛ API-key profile تي اهو usage
error (exit code 1) ڏئي ٿو، ڇو ته refresh token موجود نه هوندو:

```sh
omi auth refresh
omi auth logout
```

Default configuration `~/.omi/config.toml` ۾ محفوظ ٿئي ٿي. ان فائل کي شيئر نه
ڪريو، ڇو ته ان ۾ credentials ٿي سگهن ٿا.

## يادگيريون ۽ ڳالهيون پڙهڻ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ڪنهن هڪ ڳالهه جو transcript به پڙهي سگهجي ٿو:

```sh
omi conversation get <CONVERSATION_ID> --include-transcript
```

مقصد جي نئين progress لاءِ مقصد جو ID ۽ value ٻئي ڏيڻا پوندا:

```sh
omi goal progress <GOAL_ID> 25
```

خالي فهرست جو مطلب اڪثر اهو هوندو آهي ته ملندڙ شيون موجود ناهن؛ filters ڏسڻ
لاءِ help استعمال ڪريو:

```sh
omi memory list --help
omi conversation list --help
omi action-item list --help
```

## JSON ۽ صفحا

`--json` global اختيار آهي، تنهنڪري ان کي verb کان **اڳ** رکو:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

پهرين ڪمانڊ پهريان 25 records ۽ ٻي ايندڙ 25 records گهري ٿي. هڪ page مڪمل
backup نه آهي. JSON ۾ مڪمل IDs رهندا آهن، جڏهن ته table ڏيکاري وقت IDs مختصر
ٿي سگهن ٿا.

فائل ۾ محفوظ ڪرڻ وقت exit status به جانچيو:

```sh
if omi --json memory list --limit 25 --offset 0 > memories-page-1.json; then
  echo "export مڪمل ٿيو"
else
  echo "export ناڪام ٿيو" >&2
fi
```

Export ٿيل فائل ۾ ذاتي معلومات ٿي سگهي ٿي؛ ان کي private رکو. `--json` لاءِ
صحيح ترتيب `omi --json memory list` آهي، نه `omi memory list --json`.

## Profiles

هر profile جو پنهنجو API base ۽ authentication method ٿي سگهي ٿو:

```sh
omi config profile list
omi --profile personal auth login
omi --profile work auth login --api-key omi_dev_...
omi --profile work memory list
```

Profile چونڊڻ جي precedence هي آهي: command-line `--profile`، پوءِ
`OMI_PROFILE`، پوءِ config جو active profile:

```sh
export OMI_PROFILE=work
omi conversation list
```

## مقامي Desktop API (اختياري)

Omi Desktop هلندڙ هجي ته local API جي حالت ڏسو يا screen history ڳوليو:

```sh
omi --json local status
omi --json local search-screen "pricing page" --days 7 --app Safari
```

Local endpoint لاءِ `OMI_LOCAL_API_URL` ۽ `OMI_LOCAL_TOKEN` environment variables
استعمال ڪري سگهجن ٿا. اهي cloud API credentials کان الڳ آهن.

## Exit codes

Automation ۾ هي stable exit-code contract استعمال ڪريو:

| Code | مطلب | عام قدم |
| :---: | :--- | :--- |
| `0` | ڪاميابي | نتيجو استعمال ڪريو |
| `1` | usage/validation error | command ۽ arguments درست ڪريو |
| `2` | authentication error | `omi auth login` يا credentials چيڪ ڪريو |
| `3` | server/network error | connection چيڪ ڪري ٻيهر ڪوشش ڪريو |
| `4` | rate limited (429) | ٻڌايل وقت تائين انتظار ڪريو |
| `5` | not found (404) | ID يا endpoint چيڪ ڪريو |

وڌيڪ commands ۽ مڪمل options لاءِ [انگريزي مکيه رهنمائي](../README.md) ۽
`omi --help` ڏسو.
