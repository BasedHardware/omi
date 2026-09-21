# Primme passe cu omi-cli

Sta guida te fa ncummencia cu omi-cli, scritta in napulitano. 'E nomme d''e cumande e 'e mmasciate d''o prugramma rummano 'n ngrese. 'E esempie 'e sta guida nun cagnano 'e ricuorde, 'e cunversaziune, 'e azione o 'e ubbiettive tuje.

## 'A nstallazione

Te serve Python 3.10 o cchiù, e nu cunto Omi.

Si `pipx` ce stà già:

```sh
pipx install omi-cli
omi --help
```

O sinò 'o può nstallà int'a nu Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Si 'o terminal nun truova `omi`, verifica si 'o virtual environment sta appicciato o si 'a cartella 'e `pipx` sta dint'a `$PATH`.

## Cummerte 'o cunto tujo

Accummenza 'o wizard 'e login interattivo:

```sh
omi auth login
```

Può scigliere: trasi cu 'o browser o 'ncollà na API key 'e sviluppatore Omi. 'O input interattivo ncóva 'a chiave; statte attiento, nun 'a lassà dint''a storia d''o terminal.

Pe trasí direttamente cu 'o browser:

```sh
omi auth login --browser
```

Trasa 'ncopp''a stessa machina addó' sta 'o terminal: 'a risposta 'e l'autorizzazione usa n'indirizzo locale. Siqui 'e nstruziune 'ncopp''o schermo.

Mò verifica 'a configurazione e 'a API key:

```sh
omi auth status
omi auth whoami
```

`status` fa vedé 'o stato locale e ncóva 'e segrete, ma nun verifica 'ncopp''o server. `whoami` manna na richiesta autorizzata; si va buono, 'o ssaje ca 'e credenziale tuje faticano, ma nun te fa vedé 'o nomme tujo.

'A configurazione sta dint'a `~/.omi/config.toml`. Nun spartí stu file: ce ponno stà 'e segrete 'e trasuta.

## Vire 'e date

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lista vacante può significà sempricemente ca nun ce stanno date ca corrispónneno 'a dumanda. Pe 'mparà 'e filtre 'e ogne cumanna, vire 'o aiuto:

```sh
omi memory list --help
omi action-item list --help
```

## 'O JSON e 'e pàggene

Métte ll'opzione globale `--json` **primma** d''o gruppo 'e cumanna:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

'A primma cumanna piglia 'e primme 25 ricuorde; 'a seconna piglia ll'ate 25. Na pàggena spisso nun è china. 'O JSON fa vedé tutte ll'identificature, mentre 'e tàvule 'ncopp''o schermo spisso 'e scurciano.

Pe scrivere na pàggena int'a nu file:

```sh
omi --json memory list --limit 25 --offset 0 > ricuorde-pàggena-1.json
```

'O redirect crea nu file locale o 'o scrive ncopp'a nu file ca ce steva. Verifica ca 'a cumanna è ghjuta buono primma 'e usà 'o cuntenuto. Ll'errore vanno ncopp''a stderr; nu file vacante nun vò dicere ca nun ce stanno date. 'E file esportate ponno tené 'e segrete: astipàlele a sicuro.

## Ascì

```sh
omi auth logout
```

Sta cumanna leva 'e credenziale astipate 'ncopp''a machina. Pe scancellà 'a chiave 'ncopp''o server, usa 'a gestione d''e chiave 'e sviluppatore dint''o cunto tujo.

Pe ati cumanne e opzione avanzate, vire ['a guida principale ngrese](../README.md) e `omi --help`.
