import os
import subprocess

from pydub import AudioSegment

os.environ['SONIOX_API_KEY'] = ''


def add_speaker():
    result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--add_speaker', '--speaker_name', 'test_1'])
    completed = result.returncode == 0
    print('add_speaker:', result)
    return completed


def remove_speaker():
    result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--remove_speaker', '--speaker_name', 'test_1'])
    completed = result.returncode == 0
    print('remove_speaker:', result)
    return completed


def remove_training_sample():
    result = subprocess.run(
        [
            'python', '-m', 'soniox.manage_speakers', '--remove_audio', '--speaker_name', 'test_1', '--audio_name',
            'joined_output'
        ]
    )
    completed = result.returncode == 0
    print('remove_training_sample:', result)
    return completed


def train_speaker_profile():
    files_to_join = []
    for sample in os.listdir('data/final_samples/'):
        if '.wav' not in sample:
            continue
        path = f'data/final_samples/{sample}'
        files_to_join.append(AudioSegment.from_file(path))

    output = files_to_join[0]
    for audio in files_to_join[1:]:
        output += audio  # This concatenates it wrong, it's twice the duration it should be

    output_path = 'data/final_samples/joined_output.wav'
    if os.path.exists(output_path):
        os.remove(output_path)
    output.export(output_path, format='wav')

    result = subprocess.run(
        [
            'python', '-m', 'soniox.manage_speakers', '--add_audio', '--speaker_name', 'test_1', '--audio_name',
            'joined_output', '--audio_fn', output_path
        ]
    )
    completed = result.returncode == 0
    print('train_speaker_profile:', result)
    return completed


def speaker_exists(uid: str):
    result = subprocess.run(['python', '-m', 'soniox.manage_speakers', '--list'], capture_output=True)
    exists: bool = f"'name': '{uid}'" in str(result.stdout)
    print(f'speaker {uid} exists:', exists)
    return exists


def execute():
    # remove_speaker()
    # add_speaker()
    # remove_training_sample()
    # train_speaker_profile()
    speaker_exists('test_12')


if __name__ == '__main__':
    execute()
