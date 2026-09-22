# Exportar conversaciones de Omi a Markdown (Obsidian / Notion / Segundo Cerebro)

Utiliza esta receta para exportar las transcripciones y resúmenes de tus conversaciones de Omi a archivos Markdown limpios y estructurados. Los archivos resultantes vienen preconfigurados con encabezados YAML (frontmatter), listas de verificación de tareas pendientes y transcripciones con marcas de tiempo, listos para integrarse directamente en una bóveda de **Obsidian**, **Notion**, **Logseq** o un archivo personal.

## Requisitos

- Python 3.10+
- Un `omi-cli` autenticado (`omi auth login`)

## Inicio rápido

### Opción 1: Canalización directa mediante Stdin (Recomendado)

Obtén tus conversaciones recientes (incluyendo los segmentos completos de la transcripción de audio) y expórtalas directamente a tu bóveda de Obsidian:

```bash
omi --json conversation list --include-transcript --limit 50 | python conversations_to_markdown.py - --output-dir ~/Documents/ObsidianVault/Omi/
```

### Opción 2: Exportar desde un archivo JSON guardado

1. Exporta las conversaciones a un archivo JSON local:
   ```bash
   omi --json conversation list --include-transcript --limit 100 > conversations.json
   ```

2. Convierte la exportación JSON en notas Markdown individuales:
   ```bash
   python conversations_to_markdown.py conversations.json --output-dir ./notes/
   ```

### Opción 3: Exportar una conversación específica individual

```bash
omi --json conversation get <CONVERSATION_ID> --include-transcript > conversation.json
python conversations_to_markdown.py conversation.json --output-dir ./notes/
```

---

## Estructura de salida

Cada archivo exportado se nombra siguiendo el patrón `AAAA-MM-DD_slugified_title_shortid.md` (por ejemplo: `2026-09-13_ai_wearables_architecture_review_conva1b2.md`).

### Ejemplo de nota exportada

```markdown
---
id: "conv-a1b2c3d4-e5f6-7890-1234-56789abcdef0"
title: "AI Wearables Architecture Review"
category: "engineering"
date: "2026-09-13T10:30:00Z"
source: "omi_necklace"
tags:
  - omi
  - conversation
  - "engineering"
---

# AI Wearables Architecture Review

**Date:** 2026-09-13 10:30:00 UTC | **Category:** `engineering` | **Source:** `omi_necklace`

## Summary

Discussion on reducing latency for real-time audio transcript streaming and integrating local on-device cache for memories.

## Action Items

- [ ] Benchmark on-device Opus compression vs raw PCM
- [x] Implement exponential backoff for Redis transcript buffer reconnects

## Transcript

> **[00:00] Speaker 0:** Good morning team, let's review the audio streaming pipeline.
>
> **[00:05] Speaker 1:** We ran benchmarks on the Opus codec and observed a 60% bandwidth reduction with sub-80ms latency.
>
> **[00:12] Speaker 0:** That's fantastic. Let's document the findings and prepare the pull request.
```

---

## Características

- **Listo para Obsidian / Notion:** Incluye encabezado YAML con etiquetas (`#omi`, `#conversation`, `#<category>`) para indexación y filtrado automático en vistas de grafo.
- **Listas de verificación interactivas:** Los elementos de acción generados por Omi se convierten en casillas de verificación estándar de Markdown (`- [ ]` y `- [x]`).
- **Transcripciones con marcas de tiempo:** Las intervenciones del diálogo tienen formato de citas legibles con atribución del hablante y marcas de tiempo formateadas `[MM:SS]` (`[HH:MM:SS]` para conversaciones de más de una hora).
- **Biblioteca estándar pura:** No requiere dependencias de terceros (no es necesario instalar nada con `pip`).
- **Manejo seguro:** Gestiona campos ausentes, caracteres especiales, codificación UTF-8 BOM y evita colisiones de archivos o problemas de salto de directorios.
