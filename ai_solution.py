```yaml
---
title: "LLM/Agent Quickstart Guide"
language: "no"
---
# Omi-CLI-agent-oppstart-hvis-for-norge

Omi-CLI er en ny og maktfull CLI-verktyk med AI-trening og -generering. Denne guide vil hjelpe deg med aa oppstarte og forstå bruk av Omi-CLI for agent-arbeidfløyer.

## Hva er Omi-CLI?

Omi-CLI er en AI-baet CLI-verktyk som støtter AI-trening og -generering. Det er spesifickut tilpasset for Norge og norsk.

## Krav

For aa bruke Omi-CLI, trenger du:

- Python 3.8 eller nyere
- Omi-CLI-pip-pakke: pip install omi-cli

## Snel oppstart

Følg disse enkelte trinn for aa bruke Omi-CLI som en agent:

1. **Oppstart**:
   - Kør kommandot:
     ```bash
     omi-cli
     ```
   - Du vil se en velkomstmelding og mulighet for aa velge en agent.
   
2. **Velj Agent**:
   - Velj "LLM/Agent" for aa skapa en agent.
   
3. **Kommunikasjon**:
   - Agenten vil forklare seg og spørke hva du vil gjøre.
   - Trygga agenten med "be unquiet" for aa slenga flere meldinger.
   
4. **Bruke som Agent**:
   - Når agenten er klar, kan du skapa og konfigurere prosesser.
   - For eksempel, skapa en ny prosess:
     ```bash
     process create "Hello World Process"
     ```
     - Så vil agenten forklare og spørke om du vil konfigurere prosessen.
     - Du kan angi input og output:
       ```bash
       input-type: text
       output-type: text
       ```
       - og så vil prosessen bli konfigurert.
     
5. **Utførte prosesser**:
   - Når prosessene er klar, kan du utføre dem:
     ```bash
     process run
     ```
   - Agenten vil utføre og vise resultatet.

6. **Hjelp og opplysninger**:
   - Hvis du trenger hjelp, bruk:
     ```bash
     help
     ```
   - For aa skapa denne guide, bruk:
     ```bash
     help create:doc
     ```
   
## Avslutning

Tusen takke for aa bruke Omi-CLI! Hvis du har spørsmål, er vi altid til hjelp.
```

```yaml
---
title: "Agent Quickstart Guide"
language: "no"
---
```