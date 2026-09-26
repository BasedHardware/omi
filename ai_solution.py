```yaml
---
title: Guida veloce per gli agenti (it)
description: Introduzione veloce agli agenti per LLM (Large Language Models) con esempi di comandi CLI in italiano.
---

# Guida veloce per gli agenti

## Panoramica degli agenti LLM

Benvenuto all'ambiente degli agenti per LLM (Large Language Models). Questa guida è dedicata all'esperienza degli agenti.

## Inizio

Per iniziare, esegui il seguente comando:

```bash
$ om --help
```

## Installazione

Esegui l'installazione con:

```bash
$ pip install "omi[all]"
```

## Esegui l'agente

Per avviare l'agente, usa:

```bash
$ om
```

## Comando CLI di esempio

Ecco un esempio di comando:

```bash
$ om --model "Claude 3"
```

## Scopri gli LLM

Esegui:

```bash
$ om --discover
```

## Registra un LLM

Per esempio:

```bash
$ om --llm claude --model "Claude 3" --api_key "your_api_key"
```

## Più di un LLM?

Se hai più LLM, esegui:

```bash
$ om --llm Claude,Cost
```

## Impostazioni di completamento

Definisci:

```bash
$ OM_LLM=claude
```

## Carta del modello

Ecco un esempio:

```bash
$ om --model card
```

## Risposta di esempio

Ecco un esempio di output:

```bash
$ om --model "Claude 3"
```

## Passaggi successivi

Per ulteriori informazioni, consulta la documentazione.

## Risorse supplementari

Altri documenti sono disponibili nella documentazione.

## About the Author

La guida è stata realizzata dagli autori.
```