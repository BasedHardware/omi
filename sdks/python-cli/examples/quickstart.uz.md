# Omi-cli Қыска Йўрнатма

Bu yo'nalish `omi-cli` komandalochniy interfeysidan foydalanishni osonlashtiradi.

## Omi-cli haqida

`omi-cli` — bu [Omi](https://omi.me) ishlab chiqaruvchi API ga kirish uchun komandalochniy interfeys. U siz haqida saqlagan asosiy 4 ma'lumot turini cheklangan, agentlar uchun moslashgan buyruqlarni taqdim etadi:

* **xotira** — sistemani bilgan faktlar va o'rganishlar
* **suhbatlar** — saqlangan va qayta ishlantirilgan audio/o'rnatish almashishlari
* **harakatlar** — vazifalar va kutilgan amallar
* **maqsadlar** — jarayonni kuzatish metrikasi

U ma'lumotlarni shablonlarga moslashtrish uchun juda kichik, skriptlanishi mumkin bo'lgan va JSON-birinchi bo'lgan — shuni orqali siz Omi-ni shell jarayonlariga, CI ishlariga, agentlar to'g'risidagi vositalarga yoki shunchaki sizning shaxsiy avtomatlashtirishingizga ulashingiz mumkin.

## O'rnatish

```bash
pipx install omi-cli            # tavsiya etiladi — ajratilgan o'rnatish
# yoki
pip install omi-cli
```

O'rnatishdan so'ng, sizning `$PATH`-da joylashgan binariya nomi `omi`:

```bash
omi --version
omi --help
```

## Kirish

```bash
# 1. Kirish. Yo'naltiruvchi belgilardan foydalangan holda, omi-cli sizga kimlikni qanday tekshirib olish kerakligini so'raydi:
omi auth login
# → 1) Brauzer — Google yoki Apple orqali rostdan ham odamlar uchun kirish (tavsiya etiladi)
# → 2) API kaliti — app.omi.me dan razishlovchi kalitni kiritish (agentlar/CI uchun tavsiya etiladi)

# 2. Ishlashni boshlash:
omi memory list
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

## Terminal suhbat

Omi profilingiz bilan kirish va joriy umumiy Omi bulut suhbat jarayonida suhbat qiling:

```bash
omi auth login --browser
omi chat                        # interaktiv; javoblar kelib kelish paytida yuboriladi
omi chat "Nimani qaror qildik?"  # bir xabar, so'ng chiqish
omi chat --history --limit 20   # eng so'nggi ulashishlar
omi chat --clear                 # ommaviy bulut suhbat tarixini o'chirish uchun so'raydi
omi chat --clear --yes           # noqonuniy interaktiv o'chirish
omi --json chat "Bugungi kunni tartiblayish"  # oxirgi javobni JSON sifatida
```

Interaktiv buyruqlar: `/history`, `/clear`, `/tasks`, `/task add TEXT`, `/task done ID`, `/help`, va `/quit`. `/clear` ommaviy bulut suhbat tarixini barcha mijozlar orasida, faqat terminal chiqishidan emas o'chiradi. Bu har doim oldidan so'raydi.

Bu bulut suhbat backendidan foydalanadi va uning sinxron xotiralari, suhbatlar va vazifalari bilan ishlaydi. U terminalni Macning maxfiy ekragini yoki faqat ish stoli bo'yicha agent kontekstiga hayotiy kirish imkoniyati bermaydi; uchun uni ish stoli ilovasidan foydalaning. Islovchi API kalitlari foydalanuvchi suhbat endpointini tekshirib olishga yetarli emas, shunday qilib `omi chat` brauzer orqali kirish talab qiladi. `omi ask` har doim cheklangan, bir marta ishlov beruvchi islovchi API-kaliti savollari uchun mavjud.

Har qanday buyruga `--json` ni qo'shing (global flag sifatida, verb oldidan) mashina o'qiladigan chiqishni olish uchun, `jq`, agent vositalariga yoki boshqa narsalarga tayyorlash uchun:

```bash
omi --json memory list | jq '.[] | {id, content}'
```

Chiqishni ko'rsatish haqiqiy matnni o'z ichiga oladi, jadvallar sonli kodlar va emoji kabi misolda `:warning:`. Stil tajribaga qo'llaniladi, emas xotira yoki suhbatlar ichidagi ma'lumotlaringizga.
Jadvallar aniq qatorlar bilan belgilangan emas, har bir qatorning birinchi qaralgan maydonlarini o'z ichiga oladi.
