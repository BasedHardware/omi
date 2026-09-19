# omi-cli ile ilk adımlar

Bu qılavuz omi-cli'nin ilk komandalarını (commands) Qırım tatar tilinde añlata. Komanda adları ve program bildirişleri ingliz tilinde qala. Bu yerde kösterilgen qıdıruv misalleri sizin hatıralarıñıznı (memories), subbetleriñizni (conversations), işleriñizni (action items) ya da maqsatlarıñıznı (goals) deñiştirmey.

## Qurmav

Kerekli: Python 3.10 ya da daa yañı, ve bir Omi esabı.

Eger `pipx` bar olsa:

```sh
pipx install omi-cli
omi --help
```

Aktiv Python virtual muhitinde de qurup ola:

```sh
python -m pip install omi-cli
omi --help
```

Eger terminal `omi` tapmasa, virtual muhitniñ işlegenini ya da `pipx` qovluğınıñ `$PATH` içinde olğanını teşkeriñiz.

## Esabıñıznı bağlav

İnteraktiv yardımcını başlañız:

```sh
omi auth login
```

Brauzer ile kirme ya da Omi developer API anahtarını qoyma arasında saylañız. İnteraktiv kirme anahtarnı saqlay; terminal tarihında qalacaq komandağa anahtarnı yazmañız.

Doğrudan brauzerge baruv içün:

```sh
omi auth login --browser
```

Terminal ile aynı kompyuterde kiriñiz: autentifikatsiya cevabı yerli adreske barır. Ekrandaki talimatlarnı taqip etiñiz.

Soñra konfiguratsiyanı ve API irişimini teşkeriñiz:

```sh
omi auth status
omi auth whoami
```

`status` yerli al-ahvalnı kösterir ve sırını saqlar, amma serverdeki kerekligini teşkermey. `whoami` autentifikatsiyalı sorav yapar; muvafaqiyetli olsa, malümatnıñ işlegeni açıq, adıñıznı köstermeden.

Konfiguratsiya adetince `~/.omi/config.toml` içinde saqlanır. Bu faylnı paylaşmañız: şahsiy malümatı bar ola bilir.

## Malümatıñıznı közetüv

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Boş liste çoq vaqıt qıdıruvğa bir şey kelişmegenini bildire. Er bir komandanıñ filtrlerini tapmaq içün yardımdan faydalanıñız:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ve saifeler

Global `--json` opsiyasını komanda gruppından **evel** qoyuñız:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Birinci komanda ilk 25 hatıranı soray; ekinci komanda soñraki 25ni. Bir saife tam kopiya degil. JSON tam sayılarnı saqlar, amma ekrandaki cedveler olarnı qısqarta bilir.

Bir saifeni faylğa saqlav içün:

```sh
omi --json memory list --limit 25 --offset 0 > hatıra-saife-1.json
```

Bu yöneltüv yerli faylnı yarata ya da üstüne yaza. İçindekini qullanmadan evel komandanıñ bitkenini teşkeriñiz. Hatalar hata çıqışına (stderr) yazıla; boş fayl malümat yoqluğınıñ ispatı degil. Eksport etilgen faylda şahsiy malümat ola bilir: onı mahrem saqlañız.

## Çıquv

```sh
omi auth logout
```

Bu komanda yerli saqlanğan malümatnı siler. Serverdeki anahtarnı kerekmez etmek içün, öz esabıñızdaki developer anahtar idaresini qullanıñız.

Daa çoq komanda ve opsiya içün, [ingliz tilindeki baş qılavuznı](../README.md) ve `omi --help` köriñiz.
