# Daj yungh omi-cli

Bonj saw neix yungh Vahcuengh gangj omi-cli aen command daih'it baez yungh. Aen command caeuq program aen vah lij dwg English. Gij laih neix mbouj gaij gij memories, conversations, action items, roxnaeuz goals mwngz.

## Ancang

Suyauq: Python 3.10 roxnaeuz aen moq lai, caeuq aen Omi account.

Danghnaeuz mwngz cang pipx:

```sh
pipx install omi-cli
omi --help
```

Roxnaeuz cang haeuj aen Python virtual environment gaifah neix bae:

```sh
python -m pip install omi-cli
omi --help
```

Coi naeuz: `omi` aen command ganhdaeuj mbouj youq $PATH mwngz gwnz — ndaej yawh aen virtual environment gaifah lij miz, roxnaeuz pipx aen wenzjag youq $PATH.

## Daenghluk

Yungh CLI gonq, daenghluk haeuj gonq:

```sh
omi auth login
```

Mwngz ndaej yungh browser daenghluk, roxnaeuz yungh Omi developer API key. Key dwg dienz haeujbae — mbouj youq haeuj terminal lizsij.

Youq aen dennauj neix gwnz, yungh browser daenghluk:

```sh
omi auth login --browser
```

Danghnaeuz aen cih miz terminal: authorization youq aen bendeiz vangjiz neix guh liux. Ciuq aen pinzmuz gangj guh.

Yawh aen swzdin caeuq API key hixneix:

```sh
omi auth status
omi auth whoami
```

`status` couh ok gij bendeiz saeb, caeuq gij secrets gip hwnj, mbouj bae cam server. `whoami` couh fah aen maez cengjgingq; baenz liux, credentials mwngz yungh ndaej.

Aen swzdin cug youq `~/.omi/config.toml`. Mbouj yungh fwngz gaij aen faj neix — ndawde miz key aen mizswiz.

## Ok gij memories caeuq conversations

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Roxnaeuz aen biauj hoeng, couh dwg lij mbouj miz dox. Yungh naej coqmingz miz gij filter, yawj:

```sh
omi memory list --help
omi action-item list --help
```

## JSON caeuq suk'ok

Aen `--json` yungh doxboenq, ndaej youq command group **gonq**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Daih'it couh ndaej aen 25 memories daih'it; daihngeih ndaej aen 25 hajlaeng. JSON suk'ok miz aen identifier cienz, aen biauj couh gaij di.

Cug youq aen faj:

```sh
omi --json memory list --limit 25 --offset 0 > memories-yez-1.json
```

Aen congdauq neix couh guh aen faj moq roxnaeuz gaij aen gonq. Yawh aen command suk'ok gonq. Aen coz bae stderr; aen faj hoeng mbouj dwg mbouj miz dox. Aen suk'ok faj ndaej miz aen saeb gaeq mwngz — yungh ndei baujhoh.

## Daenghcuk

```sh
omi auth logout
```

Aen command neix couh suj aen bendeiz credentials. Aen server gwnz key, youq aen developer key management gvanj.

Yungh naej lai command caeuq suengh: [English wenz](../README.md) caeuq `omi --help`.
