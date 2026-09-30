# omi-cli লোয়ননা অহানবা খোংচাৎ

অহানবা খোংচাৎ অসি omi-cli গী অহানবা command-sিং মৈতৈলোনদা পাংথোক্লি। Command-sিংগী মিং অমসুং প্রোগ্রামগী খুদোংচাবা ইংলিশলোনদা লৈরগনি। মফম অসিদা উৎলিবা তৌখৎলিবা মীওইখোল (memories), মরোল (conversations), থবক (action items) অমসুং লম্বী-মপুং (goals) পাংথোক্লিবা ঙমদে।

## চথারোন্নবা

মথৌ তৌবা: Python 3.10 নত্রগা মখা মরোল, অমসুং Omi account অমা।

`pipx` লৈরবদি:

```sh
pipx install omi-cli
omi --help
```

Python virtual environment অমদা চথারোন্নবা ঙম্মি:

```sh
python -m pip install omi-cli
omi --help
```

Terminal অমসুং `omi` ফংলগা লৈবদি, virtual environment হাইবা লৈরি অমসুং `pipx` চাং `$PATH` দা লৈরি হায়বসি চুম্বা তৌ।

## Account লোয়নবগী ওইপু

Interactive assistant হৌগৎলু:

```sh
omi auth login
```

Browser লোয়নবা নত্রগা Omi developer API key খুদোংলবা খল্লু। Interactive input অসি key অসি উৎলে; terminal history দা লৈবা command অমদা লেখিদে।

Browser দা চাবা হোংবদি:

```sh
omi auth login --browser
```

Terminal লৈবা computer অমদা লাক্কদু: authentication-গী পাউখুম local address দা চৎকনি। Skreen দা লৈবা পাংথোক্লিবা লোয়ন।

মখুংদা, configuaration অমসুং API access অসি চেক তৌ:

```sh
omi auth status
omi auth whoami
```

`status` নসি local পরিস্থিতি উৎলি অমসুং secret উৎলে, অদুবু server দা চুম্বা ওইরে হায়বসি চেক তৌদে। `whoami` নসি authenticated রিকোয়েস্ট তৌ; মরোল ওইরবদি, credential-sিং থবক তৌরি হায়বসি মিং উৎলদে।

Configuration অসি default দা `~/.omi/config.toml` দা খুদোংলি। File অসি পুথোকপা তৌদে: অমসুং private credential লৈবা ঙম্মি।

## মফমগী দাতা এনখোল

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

List খোনবদি নসি মথৌ ওইردে হায়বসি উৎলি। Command খুদিংগী filter চংবা ঙন্বগীদমক help লোয়নু:

```sh
omi memory list --help
omi action-item list --help
```

## JSON অমসুং পেজ

Global option `--json` অসি command group-গী **মমাংদা** থু:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

অহানবা command নসি অহানবা memory 25 সি হাৎলি; অমরম্বা নসি মখা 25 সি হাৎলি। পেজ অমা নসি পুম্নমক copy ওইদে। JSON output নসি পুম্নমক নাম্বার খুদোংলি, অদুবু skreen দা লৈবা table নসি খোংথোংলবা ঙম্মি।

পেজ অমা file অমদা থুন্নবা:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

Redirect অসি local file অমা সাজি নত্রগা হোংলি। Command লোয়নখ্রবা মমাংদা কনখ্রা ওইরি হায়বসি চুম্বা তৌ। Error সি error output (stderr) দা লেখি; File konga নসি data লৈদে হায়বগী সাক্ষী ওইদে। Export তৌখ্রবা file অমদা private মরোল লৈবা ঙম্মি: private ওইনা থু।

## তুং-IN

```sh
omi auth logout
```

Command অসি local দা খুদোংখ্রবা credential সি লৌথোক্লি। Server দা key অসি লেপ্লিবদি, নখোইগী account দা developer key management লোয়নু।

Command অমসুং option হেন্না চংনবা, [ইংলিশ মপুং লম্বী](../README.md) অমসুং `omi --help` এনখোল।
