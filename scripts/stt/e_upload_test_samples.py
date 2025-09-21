import os

import requests


def execute():
    # for every file in _samples/_recordings, upload it to localhost:8000/samples/upload
    speaker_id = ''
    # files = ['data/training/raw/' + p for p in list(sorted(os.listdir('data/training/raw')))]
    # files = files[5:10]
    files = ['data/final_samples/' + p for p in list(sorted(os.listdir('data/final_samples/')))]
    for file in files:
        if file.endswith('.wav'):
            files = {'file': open(file, 'rb')}
            response = requests.post(f'http://localhost:8000/samples/upload?uid={speaker_id}', files=files)
            print(response.json())


if __name__ == '__main__':
    execute()

# os.makedirs('data/final_samples', exist_ok=True)
# for file in files:
#     os.system(f'cp {file} data/final_samples/{file.replace("data/training/raw/", "")}')

# "I scream, you scream, we all scream for ice cream."
# "Pack my box with five dozen liquor jugs."
# "The five boxing wizards jump quickly and quietly."
# "Bright blue birds fly above the green grassy hills."
# "Fred’s friends fried Fritos for Friday's food festival."
