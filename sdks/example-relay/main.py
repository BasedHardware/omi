import asyncio

from easy_audio_interfaces.network.network_interfaces import SocketServer


async def start_server():
    print("Hello from example-relay!")
    server = SocketServer(host="0.0.0.0", port=8080)
    async with server:
        async for audio in server.iter_frames():
            print(audio)


def main():
    asyncio.run(start_server())


if __name__ == "__main__":
    main()
