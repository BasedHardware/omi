# omi-cli-mik tuluit siulleq

Una ilitsersuut omi-cli-mik tuluit siulleq (commands) nassuiaatigai. Taaguutit tuluttuupput. Uani takutinneqartut ilisimasanik (memories), oqaloqatigiinnik (conversations), sulinianik (action items) imaluunniit siunertanik (goals) allanngortitsinngillat.

## Ilinerneq

Pisariaqarpoq: Python 3.10 imaluunniit nutaampasissuaq, aamma Omi-kont.

`pipx` atorukku:

```sh
pipx install omi-cli
omi --help
```

Python-mi sammisassami ilinerneqarsinnaavoq:

```sh
python -m pip install omi-cli
omi --help
```

`omi` nanisinngippat, sammisap atornera imaluunniit `pipx`-p mapper-a `$PATH`-imi qularnaaruk.

## Kont-it attaveqaruk

Ikiorti aallartiguk:

```sh
omi auth login
```

Browserikkut iseriarnissamik imaluunniit Omi developer API napparsimamik toqqaagit. Iserfiginnermi napparsimaq nassaassaaq; terminalimi oqaluttuakkami allagitseqqinak.

Browserikkut ingerlagit:

```sh
omi auth login --browser
```

Terminalimut computer ataatsimi iseriguk: authentication-ip akissutaa local address-imut ingerlanneqarpoq. Skriinimi maleruagassat malillugit.

Kingorna naqqissuseqarnermik API-millu atuinermik misissuigit:

```sh
omi auth status
omi auth whoami
```

`status` local takuutigaaq, secret-illu nassaassaaq, kisianni serverimi misissuinngilaq. `whoami` authenticated-apersuinivoq; iluatsippat, napparsimatit atorneqartarput, atit takutinngilaq.

Naqqissuseqartitsineq default-imik `~/.omi/config.toml`-imi toqqorneqarpoq. File-una tunniumeqassanngilaq: napparsimatit nassaassaaqaat.

## Paasissutissat takukkit

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Listi manngitsuvoq: nassaartoqanngilaq. Ikiorti atorlugu filter-it nassaariaguk:

```sh
omi memory list --help
omi action-item list --help
```

## JSON aamma qupperneq

Optioni `--json` **siullermi** command group-imut:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Command siulleq memories 25 apersuivoq; aappaa 25-t ingerlaneranni. Qupperneq ataaseq copy naammassinngilaq. JSON-mi numeroqatit tamarmik nassaassaqaat; skriinimi tarfallat allanngortissinnaavaat.

Qupperneq file-imut toqqukkuk:

```sh
omi --json memory list --limit 25 --offset 0 > memories-qupperneq-1.json
```

Una redirect local file-imik sanaaq imaluunniit allanngortitsisoq. Command naammassinerata kingorna atortataruk. Kukkusut error-output-imut allanneqartarput (stderr); file manngitsuvoq data nassaartoqanngilaq. File anaaneqartoq inuup nalunaarsuutaanik nassaassaaqaaq: toqqortariaqarpoq.

## Aneruiluk

```sh
omi auth logout
```

Command-una local napparsimatit piiaatissai. Serverimi napparsimamik atuinngitsoortitsiuk: developer-key atortorissaarutaa atorlugu.

Atortorissaarutit allat takukkit: [tuluttut ilitsersuut pingasuaq](../README.md) aamma `omi --help`.
