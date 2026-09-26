```python
---
title: Quickstart Guide for Vietnamese (vi) Agent
---

# Quickstart Guide for Vietnamese (vi) Agent

Welcome to the Vietnamese (vi) agent quickstart guide! Let's get started with the Vietnamese (vi) agent.

## 1. Introduction

The Vietnamese (vi) agent provides support for the Vietnamese language. This guide will help you get started with the Vietnamese (vi) agent in the Python CLI.

## 2. Prerequisites

Before you begin, ensure you have:

- Python installed.
- The `omi` Python package installed.

## 3. Installation

Run the following command to install the `omi` package:

```bash
pip install omi
```

## 4. Basic Usage

You can start the Vietnamese (vi) agent by running:

```bash
omi agent --language vi
```

## 5. Examples

### 5.1. Basic Command

Run the Vietnamese (vi) agent:

```bash
omi agent --language vi
```

### 5.2. With JSON Output

To get JSON output, add `--json`:

```bash
omi agent --language vi --json
```

### 5.3. Verbose Output

For verbose output, use `--verbose`:

```bash
omi agent --language vi --verbose
```

## 6. Configuration

You can configure the Vietnamese (vi) agent using environment variables:

```bash
export OMI_API_KEY="your_api_key"
export OMI_LOCAL_API_URL="http://localhost:11439"
export OMI_LOCAL_TOKEN="your_local_token"
```

## 7. Rate Limits

The Vietnamese (vi) agent has rate limits:

- 120 requests per hour for the API.
- 25 requests per hour for the local API.
- 15 requests per hour for the local model.

## 8. Exit Codes

The Vietnamese (vi) agent returns exit codes:

- 0: Success
- 1: General error
- 2: Configuration error
- 3: Rate limit exceeded
- 4: API error
- 5: Internal error

## 9. Examples

### 9.1. Basic Example

Run the Vietnamese (vi) agent and get a response:

```bash
omi agent --language vi
```

### 9.2. Using JSON Output

Get the response in JSON format:

```bash
omi agent --language vi --json
```

## 10. Conclusion

Thank you for using the Vietnamese (vi) agent. We hope this guide helps you get started.

## 11. References

- [OMI Documentation](https://basedhardware.com/omi)
- [GitHub Repository](https://github.com/BasedHardware/omi)
- [Support](https://basedhardware.com/support)

---

```