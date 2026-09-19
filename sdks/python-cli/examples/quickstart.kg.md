# Kubanda kusadila omi-cli

Mukanda yai ke songa bansiku ya ntete na Kikongo. Bazina ya bansiku mpi bansangu ya luyalu ke bikala na Kingelesi. Bambandu ya kutanga yina kele awa ta soba ve bangindu, masolo, bansiku ya bisalu to balukanu na nge.

## Kutula porograme

Bambuma: Python 3.10 to ya mpa mpi konte ya Omi.

> Lukebisu: Zina ya pakete na PyPI kele **`omi-cli`**, kansi nsiku yina ke sala na nima ya kutula kele **`omi`**. Kele ti pakete ya nkaka ya kuswaswana ya kele ve ti kuwakana na zina `omi` na PyPI — kutula ve pakete yango.

Kana `pipx` metulama:

```sh
pipx install omi-cli
omi --help
```

Na mutindu ya nkaka, na kati ya kizunga ya Python ya kisalu:

```sh
python -m pip install omi-cli
omi --help
```

Kana terminal mona ve `omi`, tala kana kizunga ya virtual ke sala to kana kisika ya `pipx` kele na `PATH` na nge.

## Kuwakana ti konte na nge

Banda nsadisi ya kusolula:

```sh
omi auth login
```

Pona kukota na nzila ya browser, to pona dibaku ya kutula fungola ya Omi developer API. Kutula yai ke bumbaka fungola; kusonika ve fungola na bansiku yina ta bikala na disolo ya terminal.

Sambu na kukota mbala mosi na browser:

```sh
omi auth login --browser
```

Manisa kukota na ordinatere ya kiteso mosi yina terminal ke sala, sambu kyeleka ke vutuka na adresi ya kisika. Landa bantuma na skrini.

Na nima ya yina, tala nsobani mpi nzila ya API:

```sh
omi auth status
omi auth whoami
```

`status` ke songaka mutindu mambu kele na kisika mpi ke bumbaka bansweki, kansi yo ke talaka ve ti server. `whoami` ke tindaka nkotila ya kundimama; kununga ke tendula mikanda na nge ke sala mbote.

Nsobani ke bumbamaka na `~/.omi/config.toml`. Kabula ve dosie yai sambu yo kele ti mikanda na nge ya kinsweki.

## Tala bansangu na nge

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Kulongosola ya mpamba lenda tendula kaka kima ve me fwanana ti nkotila. Sambu na kuzaba bafiltre ya nsiku, tala lusadisu:

```sh
omi memory list --help
omi action-item list --help
```

## Baka JSON mpi balula balupangu

Tula nzila ya nene `--json` **na ntwala** ya bimvuka ya bansiku:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Nsiku ya ntete ke lombaka bimvuka 25 ya ntete; ya zole ke lombaka 25 ya ke landa. Yo yina lupangu mosi kele ve kopi ya mvimba. Bima ya JSON ke bumbaka bazina ya mvimba, kansi batablo lenda kulumusa yo.

Sambu na kubumba lupangu na dosie:

```sh
omi --json memory list --limit 25 --offset 0 > bangindu-lupangu-1.json
```

Kusoba yai ke salaka to ke yidikaka dosie ya kisika. Na ntwala ya kusadila, tala kana nsiku me nunga. Bifu ke sonikamaka na stderr; dosie ya mpamba kele ve kyeleka nde bansangu kele ve. Bumba dosie yai mbote sambu yo lenda vanda ti bansangu ya kinsweki.

## Kubasika (Log out)

```sh
omi auth logout
```

Nsiku yai ke katulaka mikanda ya kinsweki yina me bumbama awa. Sambu na kukatula fungola na server, sadila ntwadisi ya bafungola na konte na nge.

Sambu na bansiku ya nkaka mpi bansiku ya kuluta nene, tala mukanda ya nene na Kingelesi:
[../README.md](../README.md) mpi `omi --help`.
