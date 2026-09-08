# type: ignore
# Offline research script; not part of the service and not typechecked (see README.md).
import subprocess, os, json, concurrent.futures as cf, sys
from google.cloud import storage
from google.oauth2.credentials import Credentials


def main() -> None:
    tok = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()
    client = storage.Client(project="based-hardware", credentials=Credentials(tok))
    bucket = client.bucket("speech-profiles")
    files = [l.strip() for l in open("download_list.txt") if l.strip()]

    def get(rel):
        dst = os.path.join("audio", rel)
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            return "skip"
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            bucket.blob(rel).download_to_filename(dst)
            return "ok"
        except Exception as e:
            return f"ERR {rel} {e}"

    n = 0
    with cf.ThreadPoolExecutor(16) as ex:
        for r in ex.map(get, files):
            n += 1
            if r.startswith("ERR"):
                print(r, flush=True)
            if n % 250 == 0:
                print(n, flush=True)
    print("done", n)


if __name__ == "__main__":
    main()
