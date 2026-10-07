#!/usr/bin/env python3
"""Create a gzip tar bundle of Omi exported data files."""
import tarfile
import hashlib
import json
import os
import sys
import io


def build_bundle(input_dir: str, output_path: str) -> None:
          files = [
                        "memories.json",
                        "conversations.json",
                        "action_items.json",
                        "goals.json",
          ]
          manifest = {"files": []}
          with tarfile.open(output_path, "w:gz") as tar:
                        for fname in files:
                                          fpath = os.path.join(input_dir, fname)
                                          if not os.path.exists(fpath):
                                                                continue
                                                            data = open(fpath, "rb").read()
                                          sha = hashlib.sha256(data).hexdigest()
                                          manifest["files"].append({
                                              "name": fname,
                                              "sha256": sha,
                                              "size": len(data),
                                          })
                                          info = tarfile.TarInfo(name=fname)
                                          info.size = len(data)
                                          tar.addfile(info, io.BytesIO(data))
                                      manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
                        info = tarfile.TarInfo(name="manifest.json")
                        info.size = len(manifest_bytes)
                        tar.addfile(info, io.BytesIO(manifest_bytes))


if __name__ == "__main__":
          if len(sys.argv) != 3:
                        print("Usage: backup_bundle.py <input_dir> <output.tar.gz>")
                        sys.exit(1)
                    build_bundle(sys.argv[1], sys.argv[2])
