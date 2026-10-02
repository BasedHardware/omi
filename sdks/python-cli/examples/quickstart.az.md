# omi-cli ilə İlk Addımlar

Bu bələdçi ilk əmrləri Azərbaycan dilində izah edir. Əmr adları və proqram
mesajları ingilis dilində qalır. Burada göstərilən sorğu nümunələri sizin
xatirələrinizi, söhbətlərinizi, tapşırıqlarınızı və ya hədəflərinizi dəyişmir.

## Proqramın quraşdırılması

Tələblər: Python 3.10 və ya daha yeni versiya və bir Omi hesabı.

Əgər `pipx` quraşdırılıbsa:

```sh
pipx install omi-cli
omi --help
```

Alternativ olaraq, aktivləşdirilmiş Python virtual mühitində (virtual environment)
quraşdıra bilərsiniz:

```sh
python -m pip install omi-cli
omi --help
```

Əgər terminal `omi` əmrini tapmırsa, virtual mühitin aktiv olduğunu və ya `pipx`-in
icra olunan faylları quraşdırdığı qovluğun `PATH` dəyişəninizdə olduğunu yoxlayın.

## Hesabınızın qoşulması

İnteraktiv köməkçini işə salın:

```sh
omi auth login
```

Brauzer vasitəsilə daxil olmağı və ya Omi tərtibatçı API açarını yapışdırmaq
seçimini edin. İnteraktiv daxiletmə açarı gizlədir; onu terminal tarixçəsində
qalacaq bir əmrdə yazmaqdan çəkinin.

Birbaşa brauzerə keçmək üçün:

```sh
omi auth login --browser
```

Terminalın işlədiyi eyni kompüterdə daxil olun: autentifikasiya cavabı yerli
ünvandan istifadə edir. Ekrandakı təlimatlara əməl edin.

Bundan sonra konfiqurasiyanı və API-yə çıxışı yoxlayın:

```sh
omi auth status
omi auth whoami
```

`status` yerli vəziyyəti göstərir və sirri gizlədir, lakin serverdə etibarlılığı
yoxlamır. `whoami` autentifikasiya olunmuş sorğu göndərir; uğurlu olarsa, adınızı
mütləq göstərmədən etimadnamələrin işlədiyini təsdiqləyir.

Konfiqurasiya standart olaraq `~/.omi/config.toml` faylında saxlanılır. Bu faylı
başqaları ilə paylaşmayın: tərkibində məxfi etimadnamələriniz ola bilər.

## Məlumatlarınıza baxış

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Boş siyahı sadəcə sorğuya uyğun heç bir elementin olmadığını göstərə bilər.
Hər bir əmrin filtrlərini öyrənmək üçün köməkdən istifadə edin:

```sh
omi memory list --help
omi action-item list --help
```

## JSON formatının alınması və səhifələrin idarə edilməsi

Qlobal `--json` seçimini əmrlər qrupundan **əvvəl** yerləşdirin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Birinci əmr ilk 25 xatirəni, ikincisi isə növbəti 25-ni tələb edir. Beləliklə,
tək bir səhifə tam ehtiyat nüsxə (backup) deyil. JSON çıxışı tam identifikatorları
qoruyur, ekrandakı cədvəllər isə onları göstərmək üçün qısalda bilər.

Səhifəni faylda saxlamaq üçün:

```sh
omi --json memory list --limit 25 --offset 0 > xatireler-sehife-1.json
```

Bu yönləndirmə yerli faylı yaradır və ya əvəz edir. Məzmunu istifadə etməzdən əvvəl
əmrin uğurla başa çatdığından əmin olun. Xətalar xəta çıxışına (stderr) yazılır;
boş fayl məlumatın olmadığına zəmanət vermir. İxrac edilmiş fayl şəxsi məlumatları
ehtiva edə bilər: onu məxfi saxlayın.

## Hesabdan çıxış (Logout)

```sh
omi auth logout
```

Bu əmr yerli olaraq saxlanılan etimadnamələri silir. Serverdə açarı ləğv etmək üçün
hesabınızdakı tərtibatçı açarlarının idarə edilməsindən istifadə edin.

Digər əmrlər və qabaqcıl seçimlər üçün [ingilis dilindəki əsas bələdçiyə](../README.md)
və `omi --help` əmrinə baxın.
