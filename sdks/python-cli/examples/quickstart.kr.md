# Kakkadə Təranmaro Kəl-kəl omi-cli Bero

Kakkadə adəye amurwa buro-buroye Kanuri lan `omi-cli` bə bayanna zəyin. Su amurwaye kuru kəla porogəramyeye Nasara lan daji. Kəska koroye adəlan fəladanadaye kəla maana kakkadənəmye (memories), mana kəlaye (conversations), cida diwalanadaye (action items), aw kəriwənəmye (goals) falanjinba.

## Porogəram Kəl-kəl Diwo (Installation)

Dowa bəzayendaye: Python 3.10 aw kəma bəlinye kura Omi akauntye kəl-kəl.

Agəi `pipx` sətana:

```sh
pipx install omi-cli
omi --help
```

Kuru fando daji cida diwo Python dunya cidalan cidajin (virtual environment) lan:

```sh
python -m pip install omi-cli
omi --help
```

Agəi amur `omi` təminallan bawono, virtual environment cidajinba gənyi `pipx` bərbərnəm `$PATH` lan mbeji kuro koro.

## Akauntnəm Kəl-kəl Kalangiro (Authentication)

Kəl-banama mana kəlaye badiro:

```sh
omi auth login
```

Burawza lan kashiduro aw Omi developer API key nəm bəkno. Kəl-banama adəye kəla asir kənəm bə gənatə; amurwa təminal tarilan dajin lan kəl-kəl kənəm rubəminba.

Suro burawzaro cidayen leworo:

```sh
omi auth login --browser
```

Kafuta təminal cidajin lan sətanam burawzalan gawi: kəla tabbattoye fando adəres laruye kəl-kəl. Kəska sikirinyelan fəladanadaye dondoo.

Daji, kəl-kəl diwo kuru kəla API lewo koro:

```sh
omi auth status
omi auth whoami
```

`status` fando larulan kəla bayanna zəyin kuru asir gənanji, amma saabalan cidajinba kuro korojinba. `whoami` dowa tabbatanaro kowonji; agəi bərəgə lan sətana, sunəm fəlannjinba kəla tabbatto sətana koro.

Kəl-kəl diwo daji `~/.omi/config.toml` lan gənanada. Faile adə amuro bəladaminba: suro adəlan kəla asir kura mbeji.

## Kəla Kakkadə Koro (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Kakkadə kowo bawonaye maananzi wande kəla koroyelan awo bawono. Kəl-bana cida di amur kəl-kəl lan dowa kororo:

```sh
omi memory list --help
omi action-item list --help
```

## JSON Fando Kuru Kakkadə Balte (Pagination)

Dowa dunya kəl-kəl `--json` **fuwulan** amurwa kashiyalan gəne:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Amur buronadaye kakkadə buro 25 kowonji; kən indiyaye 25 fuwulan gowonji. Kakkadə tiloye kakkadə sammaye (backup) gənyi. JSON fando su sammaye kəl-kəl gənanji, amma sikirin tebur kəla fəlaro gənajin.

Kakkadə tilo failelan gənatəro:

```sh
omi --json memory list --limit 25 --offset 0 > kakkade-tilo-1.json
```

Dowa adəye faile larulan kəl-kəl zəyin aw falanzin. Kəla amurye bərəgə lan daji koro suro cida diwuro. Kəla bawonadaye daji kəla kowoye (stderr) lan rubozin; faile kowo bawonaye maananzi daji awo bawono gənyi. Faile sətanam kəla kənəmye mbeji: kəl-kəl gənatə.

## Akauntlan Koltə (Logout)

```sh
omi auth logout
```

Amur adəye kəla tabbatto larulan gənanadaye gənanji. Kənəm saabalankal koltəro, developer key kura akauntnəmlan cida di.

Amurwa gadaye kuru awo gadaye kəlaro, [Nasara kakkadə kura](../README.md) kuru `omi --help` koro.
