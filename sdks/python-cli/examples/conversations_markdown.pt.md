# Exportar conversas do Omi para Markdown (Obsidian / Notion / Segundo Cérebro)

Use esta receita para exportar transcrições e resumos de conversas do Omi em arquivos Markdown limpos e estruturados. Os arquivos resultantes vêm pré-configurados com frontmatter YAML, listas de itens de ação e transcrições com carimbo de data/hora, prontos para colocar diretamente em um cofre **Obsidian**, **Notion**, **Logseq** ou arquivo pessoal.

## Requisitos

- Python 3.10+
- Um `omi-cli` autenticado (`omi auth login`)

## Início rápido

### Opção 1: Pipeline direto via stdin (recomendado)

Busque suas conversas recentes (incluindo segmentos completos de transcrição de áudio) e exporte diretamente para o seu cofre Obsidian:

```bash
omi --json conversation list --include-transcript --limit 50 | python conversations_to_markdown.py - --output-dir ~/Documents/ObsidianVault/Omi/
```

### Opção 2: Exportar a partir de um arquivo JSON salvo

1. Exporte as conversas para um arquivo JSON local:
   ```bash
   omi --json conversation list --include-transcript --limit 100 > conversations.json
   ```

2. Converta a exportação JSON em notas Markdown individuais:
   ```bash
   python conversations_to_markdown.py conversations.json --output-dir ./notes/
   ```

### Opção 3: Exportar uma única conversa específica

```bash
omi --json conversation get <CONVERSATION_ID> --include-transcript > conversation.json
python conversations_to_markdown.py conversation.json --output-dir ./notes/
```

---

## Estrutura de saída

Cada arquivo exportado é nomeado com o padrão `YYYY-MM-DD_slugified_title_shortid.md` (ex.: `2026-09-13_ai_wearables_architecture_review_conva1b2.md`).

### Exemplo de nota exportada

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

## Recursos

- **Pronto para Obsidian / Notion:** Inclui frontmatter YAML com tags (`#omi`, `#conversation`, `#<category>`) para indexação e filtragem automáticas em visualizações de grafo.
- **Listas interativas:** Itens de ação gerados pelo Omi são convertidos em caixas de seleção Markdown padrão (`- [ ]` e `- [x]`).
- **Transcrições com carimbo de data/hora:** As falas do diálogo são formatadas como citações legíveis com atribuição de falante e carimbos `[MM:SS]` (`[HH:MM:SS]` para conversas com mais de uma hora).
- **Biblioteca padrão pura:** Não requer dependências de terceiros (não precisa de `pip` install).
- **Manuseio seguro:** Lida com campos ausentes, caracteres especiais, codificação UTF-8 com BOM e evita colisões de arquivos ou travessia de diretórios.
