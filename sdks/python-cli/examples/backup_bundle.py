#!/usr/bin/env python3
import tarfile, hashlib, json, os, sys

def build_bundle(input_dir, output_path):
      files = ["memories.json", "conversations.json", "action_items.json", "goals.json"]
      manifest = {"files": []}
      with tarfile.open(output_path, "w:gz") as tar:
                for fname in files:
                              fpath = os.path.join(input_dir, fname)
                              if not os.path.exists(fpath):
                                                continue
                                            data = open(fpath, "rb").read()
                              sha = hashlib.sha256(data).hexdigest()
                              manifest["files"].append({"name": fname, "sha256": sha, "size": len(data)})
                              info = tarfile.TarInfo(name=fname)
                              info.size = len(data)
                              tar.addfile(info, io.BytesIO(data))
                          manifest_bytes = json.dumps(manifest, indent=2).encode()
                info = tarfile.TarInfo(name="manifest.json")
                info.size = len(manifest_bytes)
                tar.addfile(info, io.BytesIO(manifest_bytes))

  if __name__ == "__main__":
        build_bundle(sys.argv[1], sys.argv[2])
    
