# Exportar elementos de acción de Omi a Markdown (Obsidian / Notion / Segundo Cerebro)

Utiliza esta receta para exportar y sincronizar los elementos de acción capturados por tu dispositivo portátil Omi en listas de verificación Markdown limpias e interactivas. Los archivos resultantes incluyen encabezados YAML (frontmatter), casillas de verificación de tareas estándar de GFM (`- [ ]` / `- [x]`), fechas de vencimiento y enlaces a las conversaciones de origen, listos para **Obsidian**, **Notion**, **Logseq** o bóvedas personales de tareas.

---

## Requisitos previos

Asegúrate de tener instalada y autenticada la CLI de `omi`:

```sh
pip install omi-cli
omi auth login
```

Verifica que puedes listar tus elementos de acción:

```sh
omi action-item list
```

---

## Inicio rápido

### 1. Exportación directa por canalización (Stdout)

Genera Markdown directamente desde el flujo de salida de la CLI:

```sh
omi --json action-item list | python action_items_to_markdown.py -
```

### 2. Exportar a un archivo dedicado de tareas

Exporta tus tareas en una sola nota Markdown (por ejemplo, para una bóveda de Obsidian o importación en Notion):

```sh
omi --json action-item list | python action_items_to_markdown.py - --output ~/vault/Tasks.md
```

### 3. Filtrar por estado (Solo tareas pendientes)

Exporta únicamente elementos de acción abiertos y pendientes:

```sh
omi --json action-item list --open | python action_items_to_markdown.py - --status open --output ~/vault/PendingTasks.md
```

### 4. Agrupar por fecha de vencimiento en notas diarias

Divide los elementos de acción en notas separadas por día o fecha en una carpeta:

```sh
python action_items_to_markdown.py action_items.json --output-dir ./vault/daily-tasks/ --group-by date
```

---

## Opciones de la CLI

| Opción | Indicador | Descripción | Predeterminado |
| :--- | :--- | :--- | :--- |
| `input` | Posición 1 | Ruta al archivo JSON, o `-` para stdin | *(Requerido)* |
| `--output` | `-o` | Ruta del archivo de salida (escribe todos los elementos aquí) | `stdout` |
| `--output-dir` | `-d` | Directorio de salida para escribir archivo(s) Markdown | `None` |
| `--status` | `--status` | Filtrar elementos: `all`, `open` o `completed` | `all` |
| `--group-by` | `--group-by` | Estrategia de agrupación: `status`, `date` o `none` | `status` |
| `--title` | `--title` | Título de encabezado personalizado para la nota | `"Omi Action Items"` |

---

## Estructura de salida

### Ejemplo de nota exportada (`Tasks.md`)

```markdown
---
type: action-items
total: 3
open: 2
completed: 1
exported_at: "2026-09-14T15:00:00+00:00"
tags:
  - omi
  - action-items
  - tasks
---

# Omi Action Items

> **Summary:** 2 open, 1 completed (3 total). Exported from Omi CLI.

## 📌 Pending Tasks

- [ ] Email quarterly financial update to investment team
  *(📅 Due: 2026-09-15 18:00 UTC · 🔗 [[conversation_a1b2c3d4]] · `#act_99182`)*
- [ ] Review pull request for memory sync latency optimization
  *(🔗 [[conversation_e5f6g7h8]] · `#act_99183`)*

## ✅ Completed Tasks

- [x] Configure Luno exchange sell limit order for portfolio rebalancing
  *(📅 Due: 2026-09-14 05:30 UTC · `#act_99180`)*
```

---

## Flujos de trabajo de integración

### Sincronización con la bandeja de entrada de Obsidian

Agrega esta sola línea a tu script de inicio diario o tarea cron para anexar automáticamente nuevos elementos de acción a tu bandeja de entrada de Obsidian:

```sh
omi --json action-item list --open | python action_items_to_markdown.py - --status open --output ~/Documents/Obsidian/Inbox/OmiTasks.md
```

### Importación en Notion

1. Ejecuta:
   ```sh
   omi --json action-item list | python action_items_to_markdown.py - --output omi_tasks.md
   ```
2. En Notion, abre cualquier página, haz clic en **Importar** en la barra lateral o menú, selecciona **Markdown y CSV** y elige `omi_tasks.md`. Notion convertirá automáticamente las casillas de verificación en elementos interactivos de lista de tareas (To-Do).

---

## Principios de diseño

- **Cero dependencias de terceros:** Utiliza exclusivamente módulos de la biblioteca estándar (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`).
- **Seguro y resiliente:** Gestiona automáticamente UTF-8 con BOM (Byte Order Mark) emitido frecuentemente en Windows PowerShell.
- **Protección contra salto de directorios:** Desinfecta todos los componentes de fecha y título contra ataques de salto de directorio (path traversal).
- **Listo para Segundo Cerebro:** Utiliza encabezados YAML estándar compatibles con Obsidian Dataview, Logseq y Notion.
