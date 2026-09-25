# Guaraní: Guía Rápida de Inicio para Agentes con OMI-CLI

**Agentes Inteligentes con OMI**

Esta guía muestra cómo usar el agente de IA integrado en `omi-cli` para flujos de trabajo automatizados.

---

## Requisitos Previos

1. Instale Python 3.8+ y pip:
   ```bash
   python3 --version
   pip3 --version
   ```

2. Instale OMI-CLI:
   ```bash
   pip3 install omi-cli
   ```

---

## Configuración Básica

1. Inicie sesión con su clave privada:
   ```bash
   omi login --private-key SUA_CHAVE_PRIVADA_AQUI
   ```

2. Verifique su configuración:
   ```bash
   omi config show
   ```

---

## Ejemplo de Flujo de Trabajo con Agente

### 1. Crear un Agente Personalizado

```python
from omi import Agent

class MyAgent(Agent):
    def __init__(self):
        super().__init__(name="MiAgente", description="Ejemplo de agente en Guaraní")

    def execute(self, task):
        return f"Completado: {task} en Guaraní"

agent = MyAgent()
```

### 2. Ejecutar el Agente

```bash
omi agent run --name "MiAgente" --task "Procesar datos"
```

### 3. Monitorear la Ejecución

```bash
omi agent logs --name "MiAgente"
```

---

## Comandos Útiles

| Comando                          | Descripción                                  |
|----------------------------------|----------------------------------------------|
| `omi agent list`                | Lista todos los agentes disponibles         |
| `omi agent create --file agent.py` | Crea un agente desde un archivo Python     |
| `omi agent delete --name NAME`   | Elimina un agente específico               |

---

## Solución de Problemas

- **Error de autenticación**: Verifique su clave privada con `omi config show`.
- **Agente no encontrado**: Use `omi agent list` para confirmar el nombre.
- **Permisos insuficientes**: Ejecute `omi login` nuevamente con una clave válida.

---

## Recursos Adicionales

- [Documentación Oficial de OMI-CLI](https://docs.basedhardware.com)
- [Ejemplos Avanzados de Agentes](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli/examples)
