```python
import os
import json
import hashlib

def process_audio_chunks():
    manifest = []
    dir_path = input("Enter the path to the audio chunks directory: ")
    
    if not os.path.isdir(dir_path):
        print(f"Error: The directory '{dir_path}' does not exist.")
        return
    
    file_list = [f for f in os.listdir(dir_path) if f.endswith('.wav')]
    
    for file_name in file_list:
        file_path = os.path.join(dir_path, file_name)
        if not os.path.isfile(file_path):
            print(f"Error: The file '{file_path}' does not exist.")
            return
        
        with open(file_path, 'rb') as f:
            data = f.read()
            sha256 = hashlib.sha256(data).hexdigest()
            manifest.append({'path': file_name, 'sha256': sha256})
    
    manifest_file = os.path.join(dir_path, 'manifest.json')
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, sort_keys=True, indent=2)
    
    print(f"Successfully created manifest.json in {dir_path}")

if __name__ == "__main__":
    process_audio_chunks()
```