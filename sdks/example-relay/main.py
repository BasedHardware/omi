import asyncio

from easy_audio_interfaces.extras.local_audio import OutputSpeakerStream
from easy_audio_interfaces.network.network_interfaces import SocketServer
from omi_sdk.bluetooth import listen_to_omi


async def start_server():
    print("Hello from example-relay!")
    server = SocketServer(host="0.0.0.0", port=8080)
    output_speaker = OutputSpeakerStream()
    async with server:
        async for audio in server.iter_frames():
            print(len(audio))
            output_speaker.write(audio)


def main():
    asyncio.run(start_server())


if __name__ == "__main__":
    main()
