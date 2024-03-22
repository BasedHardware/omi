from flask import Flask, render_template
import receiver

app = Flask(__name__)

@app.route('/')
def home():
    audio_file_path = "convo.wav"  # replace with your actual audio file path
    result = receiver.process_audio_file(audio_file_path)
    return render_template('index.html', result=result)

if __name__ == '__main__':
    app.run(debug=True)