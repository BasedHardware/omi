#!/usr/bin/env python3
"""Static CV1 partition contract for #5400; not a generated NCS/link-map check."""

from pathlib import Path
import re

import yaml


def load_layout(text):
    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
            assert len(keys) == len(set(keys)), "duplicate partition field"
            return super().construct_mapping(node, deep=deep)

    return yaml.load(text, Loader=UniqueKeyLoader)


def validate(layout, dts, config):
    for name, part in layout.items():
        assert part["address"] + part["size"] == part["end_address"], f"{name}: inconsistent extent"

    # Containers overlap their members by design; only leaf allocations pack.
    for names, end in (
        (("mcuboot", "mcuboot_pad", "app", "settings_storage"), 0x100000),
        (("mcuboot_secondary", "mcuboot_secondary_1", "external_flash"), 0x200000),
    ):
        cursor = 0
        for name in names:
            part = layout[name]
            assert part["address"] == cursor, f"{name}: gap or overlap at {cursor:#x}"
            cursor = part["end_address"]
        assert cursor == end, "region not fully accounted for"

    for name in ("mcuboot_primary", "mcuboot_primary_app"):
        part = layout[name]
        members = [layout[child] for child in part["span"]]
        assert part["address"] == min(child["address"] for child in members), f"{name}: incorrect start"
        assert part["end_address"] == max(child["end_address"] for child in members), f"{name}: incorrect end"
        assert part["size"] == sum(child["size"] for child in members), f"{name}: incorrect size"

    primary = layout["mcuboot_primary"]
    secondary = layout["mcuboot_secondary"]
    assert primary["size"] == secondary["size"], "OTA slot sizes differ"
    assert secondary["share_size"] == ["mcuboot_primary"], "OTA slot must follow the primary"
    assert layout["mcuboot_primary_1"]["size"] == layout["mcuboot_secondary_1"]["size"], "network slots differ"
    for name in ("mcuboot_secondary", "mcuboot_secondary_1"):
        assert layout[name]["region"] == "external_flash", f"{name}: incorrect region"
        assert layout[name]["device"] == "DT_CHOSEN(nordic_pm_ext_flash)", f"{name}: incorrect device"

    storage = layout["settings_storage"]
    match = re.search(r"storage_partition:.*?reg\s*=\s*<\s*(0x[0-9a-fA-F]+)\s+DT_SIZE_K\((\d+)\)\s*>", dts, re.S)
    assert match, "board storage_partition not found"
    assert storage["address"] == int(match[1], 16), "NVS address differs from board DTS"
    assert storage["size"] == int(match[2]) * 1024, "NVS size differs from board DTS"
    assert storage["region"] == "flash_primary", "NVS must remain internal"
    match = re.search(r"^CONFIG_PM_PARTITION_SIZE_SETTINGS_STORAGE=(0x[0-9a-fA-F]+)$", config, re.M)
    assert match and storage["size"] == int(match[1], 16), "NVS size differs from Kconfig"
    assert re.search(r"^CONFIG_SETTINGS_NVS=y$", config, re.M), "NVS settings backend disabled"
    assert layout["app"]["end_address"] <= storage["address"], "application overlaps settings"


if __name__ == "__main__":
    firmware = Path(__file__).resolve().parents[2]
    layout = load_layout((firmware / "boards/omi/pm_static.yml").read_text())
    validate(
        layout,
        (firmware / "boards/omi/omi-cpuapp_partitioning.dtsi").read_text(),
        (firmware / "omi/omi.conf").read_text(),
    )
    print("CV1 static partition contract passed (generated NCS partitions/link map not validated)")
