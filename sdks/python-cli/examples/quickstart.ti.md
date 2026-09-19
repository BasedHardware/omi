# ቅልጡፍ መጀመሪ ብ-omi-cli

እዚ መምርሒ እዚ መሰረታዊ ትእዛዛት ብቋንቋ ትግርኛ የብርህ። ኣስማት ትእዛዛትን መልእኽትታት መደብን ብእንግሊዝኛ ይቕጽሉ። ኣብዚ ዝቐረቡ ናይ ሕቶ (query) ኣብነታት ንዝኽርታትኩም (memories)፡ ዝርርባትኩም (conversations)፡ ዕማማትኩም (action items)፡ ወይ ሸቶታትኩም (goals) ኣይቅይሩን እዮም።

## ነቲ ፕሮግራም ምጽዓን (Installation)

ዘድልዩ ነገራት፡ Python 3.10 ወይ ዝሓደሰ ስሪት ምስ ናይ Omi ኣካውንት።

`pipx` ዝተጻዕነ እንተሃልዩኩም፡

```sh
pipx install omi-cli
omi --help
```

ብኻልእ ኣማራጺ፡ ኣብ ውሽጢ ዝሰርሕ ዘሎ ናይ Python virtual environment ከተዕንዎ ትኽእሉ ኢኹም፡

```sh
python -m pip install omi-cli
omi --help
```

እቲ ተርሚናል `omi` እንተዘይረኺብዎ፡ እቲ virtual environment ንጡፍ ምዃኑ ወይ እቲ `pipx` ዝተባህለ መትሓዚ ፋይላት ኣብ ውሽጢ `$PATH` ምህላዉ ኣረጋግጹ።

## ኣካውንትኩም ምትእስሳር (Authentication)

ነቲ መስተጋብራዊ ሓጋዚ (interactive assistant) ጀምርዎ፡

```sh
omi auth login
```

ብመረብታዊ (browser) ምእታው ወይ ናይ Omi developer API ቁልፊ ምልጣፍ ምረጹ። እዚ ኣገባብ ነቲ ቁልፊ ይሓብኦ፤ ነቲ ቁልፊ ኣብ ታሪኽ ተርሚናል ዝተርፍ ትእዛዝ ካብ ምጽሓፍ ተቖጠቡ።

ብቐጥታ ናብ መረብታዊ ንምኻድ፡

```sh
omi auth login --browser
```

ተርሚናል ኣብ ዝሰርሓሉ ዘሎ ኮምፒተር ኣተዉ፡ እቲ ናይ ምርግጋጽ መልሲ ናይ ከባቢ ኣድራሻ (local address) ይጥቀም። ኣብቲ ስክሪን ዝመጽእ መምርሒታት ተኸተሉ።

ድሕሪኡ፡ ቅጥዕታትን ምብጻሕ ኤፒኣይን (API access) ኣረጋግጹ፡

```sh
omi auth status
omi auth whoami
```

`status` ናይ ከባቢ ኩነታት የርኢ ከምኡ’ውን ምስጢራት ይሓብእ፡ ግን ኣብ ሰርቨር ቅኑዕ ምዃኑ ኣየረጋግጽን። `whoami` ዝተረጋገጸ ሕቶ ይሰድድ፤ ዕዉት እንተኾይኑ፡ ሽምኩም ከየርኣየ እቶም መረዳእታታት ይሰርሑ ከምዘለዉ የረጋግጽ።

ቅጥዕታት መብዛሕትኡ ግዜ ኣብ `~/.omi/config.toml` ይዕቀቡ። እዚ ፋይል ምስ ካልኦት ኣይትካፈሉዎ፡ ምስጢራዊ መረዳእታታትኩም ክሕዝ ስለዝኽእል።

## ዳታኹም ምፍታሽ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ባዶ ዝኾነ ዝርዝር ምስቲ ሕቶ ዝሰማማዕ ነገር ከምዘየለ ጥራይ ክሕብር ይኽእል። ኣብ ነፍሲ ወከፍ ትእዛዝ መጽረዪታት ንምርካብ ሓገዝ ተጠቐሙ፡

```sh
omi memory list --help
omi action-item list --help
```

## JSON ምርካብን ገጻት ምቕያርን (Pagination)

ነቲ ዓለምለኻዊ ኣማራጺ `--json` **ቅድሚ** እቲ ናይ ትእዛዝ ጉጅለ ኣቐምጥዎ፡

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

እቲ ቀዳማይ ትእዛዝ ነተን ቀዳሞት 25 ዝኽርታት ይሓትት፤ እቲ ካልኣይ ድማ ነተን ቀጸልቲ 25። ሓደ ገጽ ምሉእ መዕቀቢ (backup) ኣይኮነን። ውጽኢት JSON ምሉእ መለለዪታት ይዕቅብ፡ ሰሌዳታት ስክሪን ግን ንምርኣይ ምቹእ ንክኸውን ከሕጽርዎ ይኽእሉ እዮም።

ሓደ ገጽ ኣብ ፋይል ንምዕቃብ፡

```sh
omi --json memory list --limit 25 --offset 0 > ዝኽርታት-ገጽ-1.json
```

እዚ ኣንፈት ምቕያር እዚ ናይ ከባቢ ፋይል ይፈጥር ወይ ይትክእ። ትሕዝቶኡ ቅድሚ ምጥቃምኩም እቲ ትእዛዝ ብዕዉት መንገዲ ምዝዛሙ ኣረጋግጹ። ጌጋታት ኣብ መውጽኢ ጌጋ (stderr) ይጸሓፉ፤ ባዶ ፋይል ዳታ የለን ማለት ኣይኮነን። ዝተላእከ ፋይል ናይ ብሕቲ ሓበሬታ ክሕዝ ይኽእል እዩ፡ ብጥንቃቐ ዓቅብዎ።

## ካብ ኣካውንት ምውጻእ (Logout)

```sh
omi auth logout
```

እዚ ትእዛዝ እዚ ኣብ ከባቢ ዝተዓቀቡ መረዳእታታት ይድምስስ። ቁልፊ ኣብ ሰርቨር ንምስራዝ፡ ኣብ ኣካውንትኩም ናይ ኣማዕባሊ ቁልፊ ምሕደራ ተጠቐሙ።

ንተወሳኺ ትእዛዛትን ዝለዓሉ ኣማራጺታትን፡ ነቲ [ዋና ናይ እንግሊዝኛ መምርሒ](../README.md) ከምኡ’ውን `omi --help` ርኣዩ።
