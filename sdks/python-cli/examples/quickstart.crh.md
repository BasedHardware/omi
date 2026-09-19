# omi-cli ile Tez Başlanğıç Reberi

Bu reber omi-cli qullanuvınıñ ilk adımlarını Qırımtatar tilinde añlata. Emir adları ve programma beyanatları İngliz tilinde qala. Bu yerde kösterilgen misaller hatıralarıñıznı (memories), laflarıñıznı (conversations), vazifeleriñizni (action items) ya da maqsatlarıñıznı (goals) deñiştirmey.

## Programmanı quruv

Talaplar: Python 3.10 ya da daa yañı versiyası ve Omi esabı.

Eger `pipx` qurulğan olsa:

```sh
pipx install omi-cli
omi --help
```

Ya da faal Python virtual environment içinde qurmaq mümkün:

```sh
python -m pip install omi-cli
omi --help
```

## Esabıñıznı bağlav

İnteraktiv muavinni başlatıñız:

```sh
omi auth login
```

Brauzer vastasınen kiriş yapmağa ya da Omi developer API açarını yapıştırmağa saylañız.

Doğrudan brauzerge keçmek içün:

```sh
omi auth login --browser
```

Soñra API irişimini teşkeriñiz:

```sh
omi auth status
omi auth whoami
```

`status` yerli al-vaziyetni köstere, `whoami` ise serverge yetkili muracaat yollap, açarlarnıñ doğruluğını tastıqlay.

## Malümatlarıñıznı közden keçirüv

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Süzgüçlerni körmek içün yardım menüsini qullanıñız:

```sh
omi memory list --help
omi action-item list --help
```

## JSON elde etüv ve saifeler boyu kezinti (Pagination)

Umumiy `--json` parametresini emir gruppasından **evel** qoyıñız:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Bir saifeni dosyege saqlamaq içün:

```sh
omi --json memory list --limit 25 --offset 0 > hatiralar-saife-1.json
```

## Esaptan çıquv

```sh
omi auth logout
```

Bu emir yerli saqlanğan kimlik bilgilerini siler.

Tafsilâtlı malümat içün [İnglizce esas qullanma](../README.md) ve `omi --help` menülerini baqıñız.
