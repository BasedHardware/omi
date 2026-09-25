# omi-cli ile ilk adımlar

Bu qılavuz, omi-cli ile ilk buyruqlarnı qırımtatar tilinde (Crimean Tatar) añlata. Buyruq adları ve program bildiruvleri İngilizce qalır. Burada kösterilgen tetkik misalleri hatıralarıñıznı (memories), qonuşmalarıñıznı (conversations), areket maddeleriñizni (action items) ya da maqsatlarıñıznı (goals) deñiştirmey.

## Qurulma

Talaplar: Python 3.10 ya da daha yañı sürüm ve bir Omi esabı.

Eger `pipx` qurulğan olsa:

```sh
pipx install omi-cli
omi --help
```

Alternativ olaraq, faal bir Python virtual muhitiniñ içine qurup olasıñız:

```sh
python -m pip install omi-cli
omi --help
```

Eger terminal `omi`ni tapmasa, virtual muhitniñ faal olğanını ya da `pipx` qurğan papkanıñ `$PATH` içinde olğanını teşkeriñiz.

## Esabıñıznı bağlav

İnteraktiv kiriş yardımcısını başlatıñız:

```sh
omi auth login
```

Brauzer ile ya da Omi developer API açarını yapıştırıp kirmekni saylañız. İnteraktiv kiriş açarıñıznı gizlider; onı terminal tarihında qaldırmaqtan saqınıñız.

Brauzer ile doğrudan kirmek içün:

```sh
omi auth login --browser
```

Terminal çalışqan aynı kompyuterde kirişiñiz: avtorizatsiya cavabı yerli bir adresni qullana. Ekrandaki talimatlarnı taqip etiñiz.

Soñ, konfiguratsiyanı ve API kirişini teşkeriñiz:

```sh
omi auth status
omi auth whoami
```

`status` yerli durumnı kösterip sırlarnı gizlider, amma sunucıda doğruluğını teşkermey. `whoami` autentifikatsiyalı bir sorav yapar; muvafaqiyetli olsa, adıñıznı açıqlamadan kredensiallarıñıznıñ çalışqanını tasdıqlay.

Konfiguratsiya, adetiy alda, `~/.omi/config.toml` içinde saqlanır. Bu faylnı paylaşmañız: içinde kiriş sırları olabilir.

## Malümatlarnı közden keçirüv

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Boş bir liste, tek, soravğa uyğun malümat yoqluğını añlata bile. Her buyruqnıñ mevcut filtrelerini ögrenmek içün yardımğa baqıñız:

```sh
omi memory list --help
omi action-item list --help
```

## JSON çıqışı ve saifeleme

Global `--json` opsiyasını buyruq gruppasından **evel** qoyuñız:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Birinci buyruq ilk 25 hatıranı soray; ekincisi keleyen 25ni. Bir saife tam bir yedek degil. JSON çıqışı butün identifikatorlarnı saqlay, ekran cedvelleri ise körüv içün olarnı qısqartıp bile.

Bir saifeni faylğa saqlamaq içün:

```sh
omi --json memory list --limit 25 --offset 0 > hatıralar-saife-1.json
```

Bu yönlendirüv yerli faylnı yarata ya da onıñ üstüne yaza. İçerikini qullanmadan evel, buyruqnıñ muvafaqiyetli bitkenini teşkeriñiz. Hatalar stderr'ge yazıla; boş bir fayl malümat yoqluğını garantiya bermey. Eksport etilgen fayl şahsiy malümat tuta bile: onı gizli saqlañız.

## Esaptan çıquv (Logout)

```sh
omi auth logout
```

Bu buyruq yerli saqlanğan kredensiallarnı siler. Sunucıda açarnı lâğu etmek içün, esabıñızdaki developer açar idaresini qullanıñız.

Başqa buyruqlar ve ileri opsiyalar içün [İngilizce esas qılavuzğa](../README.md) ve `omi --help`ke baqıñız.
