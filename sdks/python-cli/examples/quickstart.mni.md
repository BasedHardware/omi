# omi-cli দা অহানবা খোংচাৎশিং

লম্বী অসিনা মৈতৈলোনদা omi-cli গী অহানবা command শিং পাংথোক্লি। Command শিংগী মিং অমসুং প্রোগ্রামগী মেসেজ শিং ইংলিশলোনদা লৈগনি। মফম অসিদা লৈবা উদাহরণ শিংনা মেমোরি, কনভার্সেসন, এক্সন আইটেম অমসুং গোল শিং হোংদে।

## ইনস্টল তৌবা

Python 3.10 নত্রগা মখা লৈবা মরোল অমসুং Omi একাউন্ট অমা মথৌ তৌবা ওই।

`pipx` লৈরবদি:

```sh
pipx install omi-cli
omi --help
```

নত্রগা Python virtual environment অমদা ইনস্টল তৌবা ঙম্মি:

```sh
python -m pip install omi-cli
omi --help
```

Terminal অসিনা `omi` ফংলগা লৈবদি, virtual environment হাইবা লৈরি নত্রগা `pipx` গী ফোল্ডর `$PATH` দা লৈরি হায়বসি চেক তৌ।

## একাউন্ট লোয়নবগী

Interactive login wizard হৌগৎলু:

```sh
omi auth login
```

Browser দা লোয়নবা নত্রগা Omi developer API key খুদোংলবা খল্লু। Interactive input অসিনা key অসি উৎলে; terminal history দা লৈবা command অমদা লেখিদে।

Browser দা চাবা হোংবদি:

```sh
omi auth login --browser
```

Terminal লৈবা computer মফমদা লোয়নবগী ওই: authentication-গী পাউখুম local address অমা ব্যবহার তৌই। স্ক্রিন দা লৈবা পাংথোক্লিবা লোয়ন।

মখুংদা configuration অমসুং API access অসি চেক তৌ:

```sh
omi auth status
omi auth whoami
```

`status` নসি local দা লৈবা অবস্থা উৎলি অমসুং secret শিং উৎলে, অদুবু server দা চেক তৌদে। `whoami` নসি authorized রিকোয়েস্ট অমা তৌ; মরোল ওইরবদি নখোইগী credential শিং থবক তৌরি হায়বসি উৎলি, অদুবু মিং উৎলদে।

Configuration অসি `~/.omi/config.toml` দা খুদোংলি। File অসি পুথোকপা তৌদে: মফমদা private credential শিং লৈবা ঙম্মি।

## দাতা এনখোল

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

List অমা খোনবদি হায়েংগনা নখোইগী খুদিংবা শিং লৈদে হায়বসি উৎলি। Command খুদিংগী filter শিং চংনবা help লোয়নু:

```sh
omi memory list --help
omi action-item list --help
```

## JSON অমসুং পেজিং

Global option `--json` অসি command group-গী **মমাংদা** থু:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

অহানবা command অসিনা অহানবা memory 25 লৌথোক্লি; অমরম্বা অসিনা মখা 25 লৌথোক্লি। পেজ অমা খক্তা পুম্নমক ওইদে। JSON output অসিনা identifier শিং পুম্নমক থাইলি, অদুবু স্ক্রিন দা লৈবা table অসিনা মখা চেকশিন তৌই।

পেজ অমা file অমদা থুন্নবা:

```sh
omi --json memory list --limit 25 --offset 0 > মেমোরি-পেজ-1.json
```

Redirect অসিনা local file অমা সাজি নত্রগা হোংলি। Command অসি মরোল ওইরি হায়বসি চেক তৌ মমাংদা কনখ্রা ওইরি হায়বসি চুম্বা তৌ। Error শিং stderr দা চৎলি; file konga লৈবদা data লৈদে হায়বগী সাক্ষী ওইদে। Export তৌখ্রবা file অমদা private মরোল লৈবা ঙম্মি: মফম শিং লোয়নসিন তৌ।

## লোগাউট তৌবা

```sh
omi auth logout
```

Command অসিনা local দা খুদোংখ্রবা credential অসি লৌথোক্লি। Server দা key অসি cancel তৌনবা, নখোইগী একাউন্ট দা developer key management লোয়নু।

Command অমসুং option হেন্না চংনবা [ইংলিশ লম্বী](../README.md) অমসুং `omi --help` এনখোল।
