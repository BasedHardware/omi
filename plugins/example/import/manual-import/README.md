# Smart Facts Collector

A mobile-optimized web application that uses GPT-4o to intelligently extract facts from unstructured text and submit them to the OMI API.

## Features

- **GPT-4o AI-Powered Extraction**: Uses advanced AI to identify and extract meaningful facts from messy, unstructured text
- Mobile-optimized UI with AI toggle
- Multi-line text input supporting various formats
- Smart fact extraction from complex text
- Submission of each fact to the OMI API
- Detailed status updates and error handling

## Setup

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Set your OpenAI API key (required for AI-powered extraction):

```bash
# On Linux/macOS
export OPENAI_API_KEY=your_openai_api_key_here

# On Windows
set OPENAI_API_KEY=your_openai_api_key_here
```

Alternatively, you can edit the `app.py` file and replace the placeholder with your API key:

```python
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "your_openai_api_key_here")
```

3. go to Omi AI app in Appstore, create a new app with "external integration capability", and allow "facts"

<img src="https://github.com/user-attachments/assets/e3d3769a-d582-4356-b5f6-b480b99c5739" width='300'>

Go to settings, copy your App ID and create private key

<img src="https://github.com/user-attachments/assets/05ed579f-dee2-443b-818c-6bfad810595e" width='300'>


4. in app.py file, provide the app ID and private key you've generated

5. Run the Flask application:

```bash
python app.py
```

6. Open your browser and navigate to `http://localhost:5001`

## How to Use

1. Toggle AI-powered extraction on or off (on by default)
2. Enter text in the textarea - this can be:
   - Notes from a book or meeting
   - Personal learning journal entries
   - Bullet points of insights
   - Any unstructured text containing facts
3. Click the "Extract & Submit Facts" button
4. The application will:
   - Use GPT-4o to intelligently identify facts (if enabled)
   - Fall back to rule-based extraction if AI is disabled or unavailable
   - Display the extracted facts
   - Submit each fact to the OMI API
   - Show the results of the submission

## Technical Details

- The frontend is built with HTML, CSS, and JavaScript
- The backend uses Flask to serve the application and handle API requests
- GPT-4o is used for intelligent fact extraction
- Rule-based extraction serves as a fallback
- Facts are sent to the OMI API individually
- Basic rate limiting is implemented to prevent API overload

## Troubleshooting

If you encounter port conflicts:

1. You can change the port in `app.py` by modifying the line: `app.run(host='0.0.0.0', port=5001, debug=True)`
2. On macOS, port 5000 is often used by AirPlay Receiver. You can disable this service in System Preferences > Sharing.

If the AI extraction is not working:

1. Make sure you've set the OpenAI API key correctly
2. Check the terminal for any API errors
3. Try toggling to rule-based extraction as a fallback 
