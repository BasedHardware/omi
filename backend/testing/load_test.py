import os
import threading
import time
from queue import Queue

import requests

# Define a queue to hold the RPS value
rps_queue = Queue()


def get_rps():
    while True:
        try:
            rps = int(input("Enter the number of requests per second (RPS): "))
            rps_queue.put(rps)
        except ValueError:
            print("Please enter a valid number.")


def transcribe_worker(file_path, url, response_queue):
    with open(file_path, 'rb') as file:
        files = {'file': ('1719786535333-temp.wav', file, 'audio/wav')}
        response = requests.post(url, files=files)
        response_queue.put(response)


base_url = 'https://josancamon19--api-fastapi-app.modal.run'
vad_url = 'https://josancamon19--vad-vad-endpoint.modal.run/'


def transcribe():
    file_path = "test.wav"
    # url = f"{base_url}/transcribe?uid=cb0675e4-e609-45b5-9e81-e5bbeaffc6d5&language=en"
    url = f"{vad_url}"
    response_queue = Queue()

    while True:
        if not rps_queue.empty():
            rps = rps_queue.get()
            print(f"Running with {rps} RPS... Press 'S' to stop.")
            while True:
                start_time = time.time()
                threads = []

                for _ in range(rps):
                    thread = threading.Thread(target=transcribe_worker, args=(file_path, url, response_queue))
                    threads.append(thread)
                    thread.start()

                # Wait for the second to end
                elapsed_time = 0
                while elapsed_time < 1:
                    time.sleep(0.1)
                    elapsed_time = time.time() - start_time

                # Collect responses
                responses = []
                while not response_queue.empty():
                    responses.append(response_queue.get())

                # Compute and display metrics
                if responses:
                    status_codes = [res.status_code for res in responses]
                    response_times = [res.elapsed.total_seconds() for res in responses]
                    success_rate = status_codes.count(200) / len(status_codes) * 100
                    avg_response_time = sum(response_times) / len(response_times)
                else:
                    success_rate = 0
                    avg_response_time = 0

                print(f"Success rate: {success_rate:.2f}%")
                print(f"Average response time: {avg_response_time:.2f} seconds")


def stop_script():
    while True:
        cmd = input().strip().lower()
        if cmd == 's':
            # noinspection PyUnresolvedReferences,PyProtectedMember
            os._exit(0)


if __name__ == "__main__":
    rps_thread = threading.Thread(target=get_rps)
    transcribe_thread = threading.Thread(target=transcribe)
    stop_thread = threading.Thread(target=stop_script)

    rps_thread.start()
    transcribe_thread.start()
    stop_thread.start()

    rps_thread.join()
    transcribe_thread.join()
    stop_thread.join()
