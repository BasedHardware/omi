# Omi Chat Self-Improvement System

This document explains the chat self-improvement system implemented for Omi. The system continuously evaluates and improves the chat prompts used by Omi to provide better responses to users.

## Overview

The chat self-improvement system consists of the following components:

1. **Prompt Evaluation**: Evaluates the quality of Omi's responses against competitor AI systems.
2. **Prompt Improvement**: Generates improved prompts based on evaluation results.
3. **Prompt Versioning**: Manages different versions of prompts and tracks their performance.
4. **Continuous Improvement Loop**: Periodically runs the evaluation and improvement process.

## Components

### Prompt Evaluation (`utils/prompt_evaluation.py`)

This module evaluates the quality of Omi's responses against various criteria and compares them with responses from competitor AI systems like ChatGPT, Claude, and Gemini.

Key features:
- Evaluates responses on relevance, accuracy, helpfulness, naturalness, personalization, conciseness, and creativity
- Compares Omi's responses with competitor responses
- Generates improvement suggestions based on evaluation results

### Prompt Improvement (`utils/prompt_improvement.py`)

This module generates improved prompts based on evaluation results.

Key features:
- Generates improved prompts using a meta-LLM approach
- Maintains a versioning system for prompts
- Provides functions to activate, compare, and rollback prompt versions

### Database Integration (`database/prompt_improvement.py`)

This module handles storing and retrieving evaluation results and prompt versions in Firestore.

Key features:
- Stores evaluation results and prompt versions
- Retrieves active prompt versions
- Manages prompt version activation and deactivation

### Continuous Improvement Loop (`utils/prompt_improvement_loop.py`)

This module runs the evaluation and improvement process in a continuous loop.

Key features:
- Evaluates current prompts using sample conversations
- Generates improved prompts based on evaluation results
- Activates improved prompts if they perform well
- Runs the improvement cycle periodically

## Integration with Omi

The chat self-improvement system is integrated with Omi's existing chat system in `utils/llm.py`. The main prompt functions have been modified to use the improved prompts from the prompt improvement system:

- `_get_answer_simple_message_prompt`: For simple conversation messages
- `_get_qa_rag_prompt`: For question answering with retrieval augmented generation
- `_get_answer_omi_question_prompt`: For answering questions about Omi

## Running the Improvement Loop

The improvement loop can be run as a background task using the script `scripts/run_prompt_improvement.py`.

```bash
# Run the improvement cycle once
python scripts/run_prompt_improvement.py --run-once

# Run the improvement cycle continuously with a 24-hour interval
python scripts/run_prompt_improvement.py --interval 24
```

## Sample Conversations

The system uses a set of sample conversations to evaluate the prompts. These conversations cover various scenarios:

- Simple greetings
- Questions about topics
- Multi-turn conversations
- Technical questions
- Personal questions

## Future Improvements

Potential future improvements to the system include:

1. **Real API Integration**: Implement actual API calls to competitor systems instead of using mock responses.
2. **User Feedback Integration**: Incorporate user feedback on chat responses into the evaluation process.
3. **More Sophisticated Evaluation**: Add more sophisticated evaluation criteria and methods.
4. **A/B Testing**: Implement A/B testing to compare different prompt versions with real users.
5. **Prompt Customization**: Allow customization of prompts for different user segments or use cases.

## Conclusion

The chat self-improvement system provides a systematic approach to continuously improving Omi's chat capabilities. By evaluating responses, generating improved prompts, and maintaining a versioning system, the system helps Omi compete with other AI systems in the market.