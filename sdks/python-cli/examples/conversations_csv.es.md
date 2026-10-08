# Convertir una exportación de conversaciones a CSV

Usa esta receta para revisar los metadatos de las conversaciones en una hoja
de cálculo. Lee un archivo JSON guardado, no hace solicitudes de red y no
exporta transcripciones. Necesitas Python 3.10 o posterior y un `omi-cli`
autenticado para realizar la exportación inicial.

Exporta hasta 200 conversaciones:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Comprueba que el comando terminó correctamente antes de convertir el archivo.
Esta es una sola página, no una copia de seguridad completa de la cuenta. Para
obtener otra página, aumenta `--offset` en 200 y usa un nombre de archivo
distinto. Los cambios en la cuenta entre solicitudes pueden afectar la
paginación por desplazamiento; esta receta no promete una instantánea
consistente.

Ejecuta el conversor:

```sh
python sdks/python-cli/examples/conversations_to_csv.py conversations.json conversations.csv
```

Importa el resultado como texto UTF-8 delimitado por comas en Excel u otra
aplicación de hojas de cálculo. El conversor conserva los IDs completos, los
acentos, el texto entre comillas y los saltos de línea internos. Los campos
ausentes se convierten en celdas vacías; una lista vacía produce solo la fila
de encabezados. Se niega a sobrescribir un destino existente y una escritura
fallida no deja una exportación parcial. Trata el archivo exportado como datos
privados de conversaciones. Para conservar valores exactamente sin modificar,
guarda el JSON de origen; el CSV añade un apóstrofo a los valores comunes que
parecen fórmulas para que se interpreten explícitamente como texto.
