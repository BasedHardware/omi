# omi-cli dalil sari bi-al-lugha al-arabiya

> tahadath ma Omi min al-tarminall. musamma lil-bashar **wa** wukala al-dhaka al-istina i.

`omi-cli` huwa wajihat satar al-amr li-API al-mutawwirin fi [Omi](https://omi.me).
yuwfir awamir mawajuha lil-wukala tughatti arbaa masadir ra isiya tabqa omya aleiha:

* **memories** - al-haqa iq wa-al-dhakira yat allati tahfa thuha al-ni thama
* **conversations** - al-muhaadathat allati tam asr hafuha wa-mu ala jatuha
* **action items** - muhammat quayd al- amur wa-mutaba atuha
* **goals** - mu ashirat al-taqaddum allati ya-tim mutaba atuha

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **al-watha iq:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **al-shifrat al-masdariya:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. al-tathbeet

yunsah bi-astikhdam `pipx` liltathbeet al-ma uzul, li-tajanub ta arud ma a harikat python okhra.

Collecting omi-cli
  Downloading omi_cli-0.2.3-py3-none-any.whl.metadata (9.8 kB)
Requirement already satisfied: typer<1.0,>=0.12 in C:\Program Files\Python312\Lib\site-packages (from omi-cli) (0.27.2)
Requirement already satisfied: rich<15.0,>=13.7 in C:\Program Files\Python312\Lib\site-packages (from omi-cli) (14.3.4)
Requirement already satisfied: httpx<1.0,>=0.27 in C:\Program Files\Python312\Lib\site-packages (from omi-cli) (0.28.1)
Requirement already satisfied: tenacity<10.0,>=8.2 in C:\Program Files\Python312\Lib\site-packages (from omi-cli) (9.1.4)
Requirement already satisfied: pydantic<3.0,>=2.5 in C:\Program Files\Python312\Lib\site-packages (from omi-cli) (2.13.5)
Requirement already satisfied: tomli-w<2.0,>=1.0 in C:\Program Files\Python312\Lib\site-packages (from omi-cli) (1.1.0)
Requirement already satisfied: anyio in C:\Program Files\Python312\Lib\site-packages (from httpx<1.0,>=0.27->omi-cli) (4.15.1)
Requirement already satisfied: certifi in C:\Program Files\Python312\Lib\site-packages (from httpx<1.0,>=0.27->omi-cli) (2026.7.22)
Requirement already satisfied: httpcore==1.* in C:\Program Files\Python312\Lib\site-packages (from httpx<1.0,>=0.27->omi-cli) (1.0.9)
Requirement already satisfied: idna in C:\Program Files\Python312\Lib\site-packages (from httpx<1.0,>=0.27->omi-cli) (3.19)
Requirement already satisfied: h11>=0.16 in C:\Program Files\Python312\Lib\site-packages (from httpcore==1.*->httpx<1.0,>=0.27->omi-cli) (0.16.0)
Requirement already satisfied: annotated-types>=0.6.0 in C:\Program Files\Python312\Lib\site-packages (from pydantic<3.0,>=2.5->omi-cli) (0.8.0)
Requirement already satisfied: pydantic-core==2.46.5 in C:\Program Files\Python312\Lib\site-packages (from pydantic<3.0,>=2.5->omi-cli) (2.46.5)
Requirement already satisfied: typing-extensions>=4.14.1 in C:\Program Files\Python312\Lib\site-packages (from pydantic<3.0,>=2.5->omi-cli) (4.16.0)
Requirement already satisfied: typing-inspection>=0.4.2 in C:\Program Files\Python312\Lib\site-packages (from pydantic<3.0,>=2.5->omi-cli) (0.4.4)
Requirement already satisfied: markdown-it-py>=2.2.0 in C:\Program Files\Python312\Lib\site-packages (from rich<15.0,>=13.7->omi-cli) (4.0.0)
Requirement already satisfied: pygments<3.0.0,>=2.13.0 in C:\Program Files\Python312\Lib\site-packages (from rich<15.0,>=13.7->omi-cli) (2.20.0)
Requirement already satisfied: shellingham>=1.3.0 in C:\Program Files\Python312\Lib\site-packages (from typer<1.0,>=0.12->omi-cli) (1.5.4)
Requirement already satisfied: annotated-doc>=0.0.2 in C:\Program Files\Python312\Lib\site-packages (from typer<1.0,>=0.12->omi-cli) (0.0.4)
Requirement already satisfied: colorama in C:\Program Files\Python312\Lib\site-packages (from typer<1.0,>=0.12->omi-cli) (0.4.6)
Requirement already satisfied: mdurl~=0.1 in C:\Program Files\Python312\Lib\site-packages (from markdown-it-py>=2.2.0->rich<15.0,>=13.7->omi-cli) (0.1.2)
Downloading omi_cli-0.2.3-py3-none-any.whl (46 kB)
Installing collected packages: omi-cli
Successfully installed omi-cli-0.2.3

> **mulah atha: ismu hazima PyPI huwa `omi-cli` laysa `omi`.**
> * ismu al-hizma allati tuwaza au ala PyPI huwa **`omi-cli`** (al-ism al-mujarrad `omi` yakh tass li-mashru a akhar ghayr mar tub).
> * ismu adati satar al-amr ba da al-tathbeet huwa **`omi`**.

ba da al-tathbeet, tahaq q:

omi-cli 0.2.3
                                                                               
 Usage: omi [OPTIONS] COMMAND [ARGS]...                                        
                                                                               
 Omi command-line interface ¡ª talk to memories, conversations, action items,   
 and goals from your terminal. Designed for humans and agents alike. See       
 https://github.com/BasedHardware/omi for the source.                          
                                                                               
+- Options -------------------------------------------------------------------+
| --json                               Emit JSON to stdout (machine-readable, |
|                                      agent-friendly).                       |
| --profile             -p      <str>  Profile to use from                    |
|                                      ~/.omi/config.toml. Falls back to      |
|                                      $OMI_PROFILE then 'default'.           |
| --api-base                    <str>  Override the API base URL (default:    |
|                                      https://api.omi.me).                   |
|                                      [env var: OMI_API_BASE]                |
| --verbose             -v             Log HTTP traffic to stderr.            |
| --no-color                           Disable color output (also honors      |
|                                      $NO_COLOR).                            |
| --version                            Show omi-cli version and exit.         |
| --install-completion                 Install completion for the current     |
|                                      shell.                                 |
| --show-completion                    Show completion for the current shell, |
|                                      to copy it or customize the            |
|                                      installation.                          |
| --help                               Show this message and exit.            |
+-----------------------------------------------------------------------------+
+- Commands ------------------------------------------------------------------+
| version       Print the omi-cli version.                                    |
| auth          Manage authentication: login, logout, status.                 |
| config        View and modify CLI configuration / profiles.                 |
| memory        Memories ¡ª facts and learnings about the user.                |
| conversation  Conversations ¡ª captured & processed audio + text.            |
| action-item   Action items ¡ª tasks and follow-ups.                          |
| goal          Goals ¡ª tracked progress metrics.                             |
+-----------------------------------------------------------------------------+

---

## 2. tasdiq al-dukhul

`omi-cli` ya dam tughatayn li-tasdiq al-dukhul.

| tariqat al-tasdiq | mashhad al-istikhdam | al-amr |
| :--- | :--- | :--- |
| **miftah API lil-mutawwir** (`omi_dev_*`) | CI/CD, awtamta, wukala | `omi auth login --api-key ...` |
| **tasil al-dakharur min al-mutصفح** (Google/Apple) | al-istikhdam al-shakhsi yawmiyan | `omi auth login --browser` |

Choose 1 or 2 [1]: 

### miftah API

min [app.omi.me](https://app.omi.me), adh-hab ila **Developer → API Keys**.



### fahs halat al-tasdiq

          omi auth status          
 profile        default            
 authenticated  

---

## 3. qira at al-bayanat



| majmu at al-amr | al-muhtawa |
| --- | --- |
| `memory` | haqa iq wa-dhakira yat |
| `conversation` | muhaadathat |
| `action-item` | maham |
| `goal` | ahdaf wa-taqaddum |

---

## 4. JSON lil-baramej al-numaniya



### fi shell script



### fi Python



---

*an sha a bi-wasitat AUTO (wakil dhaka istinai). Bounty: Issue #13118*
