import opuslib
import numpy as np
import wave
opus_decoder = opuslib.Decoder(16000, 1)
pcm_data = bytearray()
f=[]
count = 0
with open("my_file.txt", "rb") as binary_file:
    info_char = binary_file.read()
    # print(len(info_char))
    count = int(len(info_char) / 83)

    
    for i in range(0,count):
        sample_frame = info_char[i*83:(i+1)*83]
        amount = int(sample_frame[3])
        frame_to_decode = bytes(list(sample_frame[4:4+amount]))

        f.append(frame_to_decode)
   
        # print(i)
        opus_frame = opus_decoder.decode(bytes(frame_to_decode), 160,decode_fec=False)


    for frame in f:
        try:
            decoded_frame = opus_decoder.decode(bytes(frame), 960)
            pcm_data.extend(decoded_frame)
        except Exception as e:
            print(f"Error decoding frame: {e}")
            count+=1

    with wave.open('decoded_audio.wav', 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(16000)  # Sample rate
        wav_file.writeframes(pcm_data)
# print(count)
