# Start by making sure the `assemblyai` package is installed.
# If not, you can install it by running the following command:
# pip install -U assemblyai
#
# Note: Some macOS users may need to use `pip3` instead of `pip`.

import assemblyai as aai

# Replace with your API key
aai.settings.api_key = ""
FILE_URL = "https://github.com/AssemblyAI-Community/audio-examples/raw/main/20230607_me_canadian_wildfires.mp3"
config = aai.TranscriptionConfig(speaker_labels=True, punctuate=True, auto_highlights=True)
prompt = "Provide a brief summary of the transcript."


# FILE_URL = './path/to/file.mp3'

def execute():
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(FILE_URL, config=config)

    if transcript.status == aai.TranscriptStatus.error:
        print(transcript.error)
    else:
        for utterance in transcript.utterances:
            print(
                f"Speaker {utterance.speaker}: {utterance.text} [{round(utterance.start / 1000, 2)} - {round(utterance.end / 1000, 2)}]")

        for result in transcript.auto_highlights.results:
            print(f"Highlight: {result.text}, Count: {result.count}, Rank: {result.rank}")
        # print(transcript.text)

    result = transcript.lemur.task(
        prompt, final_model=aai.LemurModel.claude3_5_sonnet
    )
    print(result.response)


def stream():
    def on_open(session_opened: aai.RealtimeSessionOpened):
        "This function is called when the connection has been established."

        print("Session ID:", session_opened.session_id)

    def on_data(transcript: aai.RealtimeTranscript):
        "This function is called when a new transcript has been received."

        if not transcript.text:
            return

        if isinstance(transcript, aai.RealtimeFinalTranscript):
            print(transcript.text, end="\r\n")
        else:
            print(transcript.text, end="\r")

    def on_error(error: aai.RealtimeError):
        "This function is called when the connection has been closed."

        print("An error occured:", error)

    def on_close():
        "This function is called when the connection has been closed."

        print("Closing Session")
#
    transcriber = aai.RealtimeTranscriber(
        on_data=on_data,
        on_error=on_error,
        sample_rate=44_100,
        on_open=on_open,  # optional
        on_close=on_close,  # optional
    )
#
#     # Start the connection
    transcriber.connect()


#
#     # Open a microphone stream
#     microphone_stream = aai.extras.MicrophoneStream()
#
#     # Press CTRL+C to abort
#     transcriber.stream(microphone_stream)
#
#     transcriber.close()


if __name__ == '__main__':
    stream()
