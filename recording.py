import os, sys
import serial
import wave, struct
import logging
import argparse

logging.basicConfig(level=logging.INFO)

commands = [b"", b"rec_ok", b"init_ok", b"fi"]

sampleRate = 16000 # hertz
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