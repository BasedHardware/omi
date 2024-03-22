import sys
import serial
import wave, struct
import logging
import argparse
from openai import OpenAI
from dotenv import load_dotenv
import os
import webbrowser
import time


load_dotenv("/Users/admin/All/audio/.env")
client = OpenAI(api_key=os.getenv("OPENAI_KEY"))
logging.basicConfig(level=logging.INFO)


commands = [b"", b"rec_ok", b"init_ok", b"fi"]
sampleRate = 8000 # hertz
duration = 10 # seconds


def write_wav_data(raw_sound, filename):
    logging.debug(raw_sound)

    obj = wave.open(filename, 'w')
    obj.setnchannels(1) # mono
    obj.setsampwidth(2)
    obj.setframerate(sampleRate)

    for value in raw_sound:
        data = struct.pack('<h', value)
        obj.writeframesraw(data)
    obj.close()


def transcribe_audio(audio_file_path):
    with open(audio_file_path, 'rb') as audio_file:
        transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file)

    return transcription.text


def key_points_extraction(transcription):
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are a highly skilled AI, adept at extracting and summarizing key information from discussions. Your primary task from the following text is to pinpoint and catalog all proper nouns, including names of people, organizations, and notable subjects, such as 'Steve Mann', 'Founders Fund', and 'Tracy's blog'. This list should encompass the most pivotal entities mentioned, providing a clear snapshot of the individuals, groups, and key topics that are central to the dialogue. Your aim is to compile a concise inventory that enables quick insight into the network of connections and main subjects addressed during the conversation."
            },
            {
                "role": "user",
                "content": transcription
            }
        ]
    )

    return response.choices[0].message.content

def process_audio_file(audio_file_path):
    transcription = transcribe_audio(audio_file_path)
    points = key_points_extraction(transcription)
    return points

def open_topics(text):
    # Base URL for a search engine, Google in this case
    base_url = "https://www.google.com/search?q="

    topics = [
        "Elon Musk",
        "Steve Jobs",
        "Tim Apple",
        "Michael"
    ]

    # Open a new browser tab for each topic
    for topic in topics:
        # Encode the topic to be URL friendly
        search_url = base_url + topic.replace(" ", "+")
        webbrowser.open_new_tab(search_url)
        # Optional: a small pause between opening each tab to reduce load on the system
        time.sleep(1)

def main(args):
    i = 1
    ser = serial.Serial(args.port, args.baud_rate, timeout=1)
    logging.info('Awaiting response from device')
    print("hte")

    while True:
        ser.write(b"init\n")
        recv = ser.readline().rstrip()
        print(recv)
        if recv == b'init_ok':
            logging.info('Device init successful')            
            break
        if recv == b'init_fail':
            logging.error('Device init failed')
            sys.exit(0)

    while True: 
        try:
            logging.info('READY') 

            input("Press Enter to continue...")
            ser.write(b"rec\n")
            logging.info('RECORDING')  
            recv = ""
            raw_sound = []

            while True:
                recv = ser.readline().rstrip()
                if recv == b"rec_ok":
                    logging.info('RECORDING FINISHED') 
                if recv == b"fi":
                    logging.info('TRANSFER FINISHED')
                    break 
                if not recv in commands:
                    raw_sound.append(int(recv))
                logging.debug(recv)

            filename = args.filename + str(i) + ".wav"
            write_wav_data(raw_sound, filename)
            key_points = process_audio_file(filename)
            open_topics(key_points)
            i += 1

        except KeyboardInterrupt:
            logging.info('Exiting script')            
            break


if __name__ == '__main__':

    argparser = argparse.ArgumentParser(
        description='Record and save sound from device')

    argparser.add_argument(
        '-p',
        '--port',
        default='/dev/tty.usbmodem1101',
        help='port for connection to the device')

    argparser.add_argument(
        '-b',
        '--baud_rate',
        default=57600,
        help='Connection baud rate')

    argparser.add_argument(
        '-n',
        '--filename',
        default='sound',        
        help='Prefix for sound files')

    args = argparser.parse_args()

    main(args)