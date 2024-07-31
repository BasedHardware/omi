from locust import HttpUser, task


class TranscribeUser(HttpUser):
    # wait_time = between(1, 10)  # You can adjust the wait time as needed
    host = 'http://localhost:8000'

    @task
    def transcribe(self):
        # Path to the audio file you want to upload
        file_path = "test.wav"
        with open(file_path, 'rb') as file:
            # Prepare the multipart/form-data payload
            files = {'file': (file_path, file, 'audio/wav')}
            response = self.client.post("/transcribe?uid=cb0675e4-e609-45b5-9e81-e5bbeaffc6d5&language=en", files=files)
            print('Status code:', response.status_code)
