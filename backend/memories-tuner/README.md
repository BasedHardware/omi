# OMI Memory Quality Tuner

A system for improving the quality of OMI's memory generation using DSPy ReAct and Langfuse for fine-tuning prompts.

## Overview

This tool enables you to:

1. **Collect memory examples** by uploading Langfuse data or manually entering conversations
2. **Label memory quality** by rating generated memories on a scale of 1-5
3. **Fine-tune prompts** using DSPy's ReAct framework and optimization techniques
4. **Test improved memory generation** with new conversations

## Setup

### Prerequisites

- Python 3.8+
- OpenAI API key

### Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables:

Create a `.env` file in the project directory with the following:

```
OPENAI_API_KEY=your_openai_api_key

# Optional: Langfuse settings (for logging)
LANGFUSE_API_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com
```

Alternatively, you'll be prompted for your OpenAI API key when running the application if it's not set.

## Running the Application

The simplest way to run the application is using the provided script:

```bash
./run.sh
```

This will:
1. Check for your OpenAI API key (and prompt for it if missing)
2. Install any missing dependencies
3. Start the Streamlit web application

You can then access the application in your browser at http://localhost:8501.

If you prefer to run manually:

```bash
streamlit run app.py
```

## Usage Workflow

### 1. Generate Memory Examples
- Use "Manual Data Entry" to input conversations and generate memories
- Or upload Langfuse export data in the "Label Memories" section

### 2. Label Memory Quality
- Rate the quality of each memory example from 1-5
- Add feedback to help identify patterns in good vs. poor memories

### 3. Tune the Prompt
- Go to "Tune Prompt" and configure the tuning parameters
- Start the tuning process (requires at least 5 high-quality examples)

### 4. Test the Improved System
- In "Test Memories," enter new conversations to see results
- Compare original vs. optimized prompts
- Save good examples for further tuning

## Troubleshooting

### OpenAI API Key Issues
- Ensure your OpenAI API key is valid and has sufficient quota
- You can input your key directly in the app's sidebar if needed

### Import Errors
- If you see import errors, try: `pip install -r requirements.txt --force-reinstall`
- Some dependency versions may need adjustment based on your Python version

### Langfuse Errors
- Langfuse logging is optional - the system will work without it
- If you want to use Langfuse, make sure your API keys are correct

### DSPy Compatibility
- This system is tested with DSPy 2.x versions
- If you encounter DSPy-related errors, check your installed version with `pip show dspy-ai`

## Technical Details

### Components

- **DSPy ReAct Framework**: Uses DSPy's ReAct reasoning capabilities to generate better memories
- **Langfuse Integration**: Logs memory generation for tracking and analysis (optional)
- **Streamlit Interface**: User-friendly labeling and tuning interface
- **Prompt Optimization**: Uses BootstrapFewShotWithRandomSearch to find optimal prompts

### Files

- `app.py`: Streamlit web application
- `dspy_react_module.py`: DSPy ReAct implementation for memory generation
- `prompt_tuner.py`: Functions for tuning and optimizing prompts
- `langfuse_logger.py`: Integration with Langfuse for logging and analysis
- `run.sh`: Helper script for running the application

## Contributing

To improve this system:

1. Collect more high-quality examples
2. Experiment with different memory quality metrics
3. Try advanced optimization strategies in DSPy

## License

This project is part of OMI and follows its licensing terms. 