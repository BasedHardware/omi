# import os
#
# os.environ['HUGGINGFACE_TOKEN'] = ''
# from utils.preprocess import preprocess_audio
#
# if __name__ == '__main__':
#     source = 'validation_3'
#     os.makedirs(f'data/{source}/cleaned', exist_ok=True)
#     for file_name in os.listdir(f'data/{source}/raw'):
#         if file_name.endswith('.wav'):
#             file_path = os.path.join(f'data/{source}/raw', file_name)
#             processed_file_path = preprocess_audio(file_path, save_dir=f'data/{source}/cleaned')
