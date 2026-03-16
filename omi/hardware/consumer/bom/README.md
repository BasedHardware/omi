# Bill of Materials — Omi Consumer

The BOM lists all 88 components needed to build one Omi device (mainboard + charger + mechanical parts).

## Files

- `omi-bom.csv` — Machine-readable CSV format
- `omi-bom.xlsx` — Spreadsheet format (cleaned)
- `omi-bom-original.xlsx` — Original manufacturer BOM

## Columns

| Column | Description |
|--------|-------------|
| ID | Sequential component number |
| SKU | Internal part SKU |
| Description | Component description with package size |
| Manufacturer | Component manufacturer |
| MPN | Manufacturer Part Number (use this to order) |
| Designator | PCB reference designator(s) |
| Qty | Quantity per unit |

## Key Components

| Component | MPN | Manufacturer |
|-----------|-----|--------------|
| Main SoC | nRF5340-CLAA | Nordic Semiconductor |
| Wi-Fi IC | nRF7002-CEAA-R7 | Nordic Semiconductor |
| Microphones (x2) | MMICT5838-00-012 | TDK |
| NAND Flash 8GB | CSNP4GCR01-DPW | CS |
| IMU | LSM6DS3TR-C | STMicroelectronics |
| Battery Charger | BQ25101YFPR | Texas Instruments |
| Battery | GRP1654M1-1C-1S1P-3.7V-150mAh | GERUIPU |
