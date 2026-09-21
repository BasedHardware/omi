# omi-cli ಒಟ್ಟಿಗೆ ಸುರುತ ಹೆಜ್ಜೆಲು

ಈ ಮಾರ್ಗದರ್ಶಿ ತುಳು ಭಾಷೆಡ್ omi-cli ತ ಸುರುತ ಕಮಾಂಡುಲೆನ್ ವಿವರಿಸುಂಡು. ಕಮಾಂಡುದ ಪುದರುಲು ಬೊಕ್ಕ ಪ್ರೋಗ್ರಾಮ್ ಸಂದೇಶೊಲು ಇಂಗ್ಲಿಷ್‌ಡ್ ಉಪ್ಪುವ. ಈ ಉದಾಹರಣೆಲು ಇರೆನ ನೆನಪುಲು, ಮಾತುಕತೆಲು, ಕ್ರಿಯೆ ವಿಷಯೊಲು ಬೊಕ್ಕ ಗುರಿಲೆನ್ ಬದಲ್ ಆಪುಜಿ.

## ಇನ್‌ಸ್ಟಾಲ್ ಮಲ್ಪುನಿ

Python 3.10 ತ ನಂತರದ ಆವೃತ್ತಿ ಬೊಕ್ಕ Omi ಖಾತೆ ಒಂಜಿ ಬೋಡು.

`pipx` ದುಂಬೇ ಇತ್ತ್ಂಡ:

```sh
pipx install omi-cli
omi --help
```

ಅತ್ತಂದೆ active Python virtual environment ಒಂಜೆಡ್ ಇನ್‌ಸ್ಟಾಲ್ ಮಲ್ಪೊಲಿ:

```sh
python -m pip install omi-cli
omi --help
```

Terminal `omi` ನ್ ಕಾಣಂದೆ ಇತ್ತ್ಂಡ, virtual environment active ಆತ್ಂಡಾ ಪರೀಕ್ಷೆ ಮಲ್ಪು; ಇಜ್ಜಿಂಡ `pipx` ತ ಫೋಲ್ಡರ್ `$PATH` ಡ್ ಉಪ್ಪೊಡು.

## ಖಾತೆನ್ ಸೇರಾವುನಿ

Interactive login wizard ನ್ ಸುರು ಮಲ್ಪು:

```sh
omi auth login
```

Browser ಡ್ login ಆಪುನಿ ಅತ್ತಂದೆ Omi developer API key ನ್ ಪೇಸ್ಟ್ ಮಲ್ಪುನಿ ಆಯ್ಕೆ ಮಲ್ಪೊಲಿ. Interactive input key ನ್ ಮುಚ್ಚುಂಡು; ಅವೆನ್ terminal history ಡ್ ದೀಯಂದೆ ಜಾಗ್ರತೆ ಮಲ್ಪು.

Browser ಡೇ ನೇರವಾದ್ login ಆಪುನಗ:

```sh
omi auth login --browser
```

Terminal ಚಾಲನೆ ಆಪುನ computer ಡೇ login ಆಲ: authorization ಪ್ರತಿಕ್ರಿಯೆ local address ಒಂಜೆನ್ ಉಪಯೋಗಿಸುಂಡು. Screen ಡ್ ತೋಜುನ ಸೂಚನೆಲೆನ್ ಪಾಲನೆ ಮಲ್ಪು.

ಇಗ configuration ಬೊಕ್ಕ API key ನ್ ಪರೀಕ್ಷೆ ಮಲ್ಪು:

```sh
omi auth status
omi auth whoami
```

`status` local ಸ್ಥಿತಿ ತೋಜುಂಡು ಬೊಕ್ಕ secret ಲೆನ್ ಮುಚ್ಚುಂಡು, ಆಂಡ server ಡ್ ಪರೀಕ್ಷೆ ಮಲ್ಪುಜ. `whoami` authorized request ಒಂಜೆನ್ ಕಳುಪುಂಡು; ಅದು ಸರಿ ಆತ್ಂಡ, credential ಲು ಬೇಲೆ ಮಲ್ಪುವ ಪಂಡ್ದ್ ತೆರಿಪುಂಡು, ಆಂಡ ಇರೆನ ಪುದರು ತೋಜುಜ.

Configuration `~/.omi/config.toml` ಡ್ ಉಪ್ಪುಂಡು. ಈ ಫೈಲ್ ನ್ ಹಂಚಂದೆ: ಅವೆಡ್ login secret ಲು ಉಪ್ಪೊಲಿ.

## ಮಾಹಿತಿನ್ ತೂಪುನಿ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ಖಾಲಿ ಪಟ್ಟಿ ಪಂಡ್ಡ್ ಇರೆನ ವಿಷಯೊಲು ಇಜ್ಜಿ ಪಂಡ್ದ್ ಅರ್ಥ. ಪ್ರತಿ ಕಮಾಂಡುದ filter ಲೆನ್ ಕಲ್ಪೆರೆ help ನ್ ತೂ:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ಬೊಕ್ಕ ಪುಟೊಲು

Global option `--json` ನ್ command group ದ **ದುಂಬು** ದೀ:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ಸುರುತ ಕಮಾಂಡು ಸುರುತ 25 ನೆನಪುಲೆನ್ ಪಡೆಪುಂಡು; ರಡ್ಡನೆಯ ಕಮಾಂಡು ಮುಂದದ 25 ನೆನ್. ಒಂಜಿ ಪುಟ ಪೂರ್ತಿ ಆಪುಜ. JSON output ಪ್ರತಿ identifier ನ್ ದೀಪುಂಡು, ಆಂಡ screen ದ table ಲು ಕೆಲವು ಬಾರಿ ಮುಕ್ಕೊಳ್ಳುವ.

ಒಂಜಿ ಪುಟ ನ್ ಫೈಲ್ ಡ್ ಬರೆಪುನಗ:

```sh
omi --json memory list --limit 25 --offset 0 > ನೆನಪುಲು-ಪುಟ-1.json
```

Redirect local ಫೈಲ್ ಒಂಜೆನ್ ಸೃಷ್ಟಿ ಮಲ್ಪುಂಡು ಅತ್ತಂದೆ ಮಿತ್ತ್ ಬರೆಪುಂಡು. ಕಮಾಂಡು ಸಫಲ ಆತ್ಂಡ ಪಂಡ್ದ್ ಖಚಿತ ಮಲ್ಪು. Error ಲು stderr ಗ್ ಪೋಪುಂಡು; ಖಾಲಿ ಫೈಲ್ ಪಂಡ್ಡ್ data ಇಜ್ಜಿ ಪಂಡ್ದ್ ಅರ್ಥ ಆಪುಜ. Export ಆಯಿನ ಫೈಲ್ ಡ್ private ಮಾಹಿತಿ ಉಪ್ಪೊಲಿ: ಅವೆನ್ ಸುರಕ್ಷಿತವಾದ್ ದೀ.

## ಲಾಗ್ ಔಟ್ ಮಲ್ಪುನಿ

```sh
omi auth logout
```

ಈ ಕಮಾಂಡು local credential ನ್ ದೆಪ್ಪುಂಡು. Server ಡ್ key ನ್ ರದ್ದು ಮಲ್ಪೆರೆ, ಇರೆನ ಖಾತೆದ developer key management ನ್ ಉಪಯೋಗಿಸುಲ.

ಬೇರೆ ಕಮಾಂಡುಲು ಬೊಕ್ಕ advanced option ಲೆಗ್ [ಇಂಗ್ಲಿಷ್ ಮುಖ್ಯ ಮಾರ್ಗದರ್ಶಿ](../README.md) ಬೊಕ್ಕ `omi --help` ನ್ ತೂಲ.
