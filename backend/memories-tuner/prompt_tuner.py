import json
import os
import dspy
from dspy.teleprompt import BootstrapFewShot, BootstrapFewShotWithRandomSearch
from dspy_react_module import MemoryReActProgram, GenerateMemories
import numpy as np
import traceback
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Optimization configuration
OPTIMIZATION_ROUNDS = 5
MIN_QUALITY_SCORE = 4  # Minimum score to consider an example high quality
LABEL_STORE_PATH = "label_store.jsonl"
OPTIMIZED_PROMPT_PATH = "optimized_prompts.json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DUMMY_MODE = os.getenv("DUMMY_MODE", "false").lower() in ("true", "1", "yes")
VALID_CATEGORIES = {'personal', 'preference', 'event', 'fact'}

# Custom metric for evaluating memory quality
def memory_quality_metric(gold, pred):
    """
    Evaluate generated memories against gold-standard memories

    This metric considers:
    - Number of memories (penalizes generating too few)
    - Memory content overlap (rewards similar content)
    - Category accuracy (rewards correct category assignment)

    Args:
        gold: Gold standard memories from labeled examples
        pred: Model-predicted memories

    Returns:
        float: Quality score between 0 and 1
    """

    
    def extract_content_and_category(memory):
        """Helper to extract content and category from memory object"""
        if isinstance(memory, dict):
            return memory.get('content', ''), memory.get('category', '')
        return memory, ''

    def get_memories_with_category(memories):
        """Process memories to handle both old and new formats"""
        if not memories:
            return []
        if isinstance(memories[0], dict):
            return [(m.get('content', ''), m.get('category', '')) for m in memories]
        return [(m, '') for m in memories]

    # Combine interesting and system memories with their categories
    gold_memories = get_memories_with_category(gold.interesting_memories + gold.system_memories)
    pred_memories = get_memories_with_category(pred.interesting_memories + pred.system_memories)

    # Check quantity match (penalize if too few memories)
    quantity_score = min(len(pred_memories) / max(len(gold_memories), 1), 1.0)

    # Calculate content and category scores
    content_scores = []
    category_scores = []
    
    for gold_content, gold_category in gold_memories:
        best_content_score = 0
        best_category_score = 0
        
        for pred_content, pred_category in pred_memories:
            # Calculate content overlap
            gold_words = set(str(gold_content).lower().split())
            pred_words = set(str(pred_content).lower().split())
            
            if gold_words:
                overlap = len(gold_words.intersection(pred_words)) / len(gold_words)
                best_content_score = max(best_content_score, overlap)
                
                # Only check category if content is somewhat similar (overlap > 0.3)
                if overlap > 0.3 and gold_category and pred_category:
                    category_match = 1.0 if gold_category.lower() == pred_category.lower() else 0.0
                    best_category_score = max(best_category_score, category_match)
        
        content_scores.append(best_content_score)
        category_scores.append(best_category_score if gold_category else 1.0)  # If no gold category, don't penalize

    # Calculate average scores
    content_score = np.mean(content_scores) if content_scores else 0
    category_score = np.mean(category_scores) if category_scores else 1.0

    # Combined score with weights
    final_score = (
        0.2 * quantity_score +  # 20% weight to quantity
        0.6 * content_score +   # 60% weight to content match
        0.2 * category_score    # 20% weight to category accuracy
    )
    
    return final_score


def load_labeled_examples(min_score=MIN_QUALITY_SCORE, file_path=LABEL_STORE_PATH):
    """
    Load labeled examples from the JSONL store

    Args:
        min_score: Minimum quality score to include (1-5)
        file_path: Path to the labeled examples file

    Returns:
        list: List of high-quality examples
    """
    examples = []

    if not os.path.exists(file_path):
        print(f"Warning: Label store file {file_path} not found.")
        return examples

    try:
        with open(file_path, "r") as f:
            for line in f:
                try:
                    example = json.loads(line)
                    if example.get("score", 0) >= min_score:
                        examples.append(example)
                except json.JSONDecodeError:
                    print(f"Warning: Skipping invalid JSON line in {file_path}")
    except Exception as e:
        print(f"Error loading examples: {e}")

    return examples


def prepare_training_data(examples):
    """Convert labeled examples to DSPy training data format"""
    training_examples = []
    for ex in examples:
        # Normalize memory format to handle both old and new formats
        interesting_memories = []
        for mem in ex["output"]["interesting_memories"]:
            if isinstance(mem, dict):
                interesting_memories.append(mem)
            else:
                interesting_memories.append({"content": str(mem), "category": "fact"})
        
        system_memories = []
        for mem in ex["output"]["system_memories"]:
            if isinstance(mem, dict):
                system_memories.append(mem)
            else:
                system_memories.append({"content": str(mem), "category": "fact"})
                
        training_examples.append(
            dspy.Example(
                context=ex["input"]["context"],
                user_name=ex["input"]["user_name"],
                interesting_memories=interesting_memories,
                system_memories=system_memories,
            )
        )
    return training_examples


def extract_base_prompt():
    """Extract base prompt instructions from the GenerateMemories class docstring"""
    docstring = GenerateMemories.__doc__
    if not docstring:
        return "Generate memories from conversation"
    return docstring.strip()


def optimize_instructions(base_instructions, examples, num_optimized=3):
    """
    Use OpenAI to generate optimized instructions based on high-quality examples

    Args:
        base_instructions: Original instructions from GenerateMemories class
        examples: List of high-quality examples
        num_optimized: Number of optimized instruction variants to generate

    Returns:
        list: List of optimized instruction variants
    """
    # If we're in dummy mode or don't have API key, return a dummy optimization
    if DUMMY_MODE or not OPENAI_API_KEY:
        print("Using dummy optimization since we're in DUMMY_MODE or missing API key")
        return [
            base_instructions + "\n\nOptimized for better memory generation with example patterns.",
        ]

    try:
        print("Optimizing instructions with OpenAI...")
        # Format examples for the prompt
        examples_text = ""
        for i, ex in enumerate(examples[:5]):  # Use up to 5 examples
            examples_text += f"\nExample {i+1}:\n"
            examples_text += f"Conversation: {ex['input']['context'][:300]}...\n"
            examples_text += f"User name: {ex['input']['user_name']}\n"
            # Handle both old format (strings) and new format (dicts with content/category)
            interesting_memories = []
            for mem in ex["output"]["interesting_memories"]:
                if isinstance(mem, dict):
                    interesting_memories.append(mem.get("content", str(mem)))
                else:
                    interesting_memories.append(str(mem))
            
            system_memories = []
            for mem in ex["output"]["system_memories"]:
                if isinstance(mem, dict):
                    system_memories.append(mem.get("content", str(mem)))
                else:
                    system_memories.append(str(mem))
            examples_text += f"Interesting memories: {', '.join(interesting_memories)}\n"
            examples_text += f"System memories: {', '.join(system_memories)}\n"
            examples_text += f"Quality score: {ex.get('score', 0)}/5\n"
            if 'feedback' in ex and ex['feedback']:
                examples_text += f"Feedback: {ex['feedback']}\n"

        # Set up OpenAI client
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        # Create the prompt for optimizing instructions
        system_prompt = """You are an expert in optimizing prompts for AI models. Your task is to analyze the original instructions for generating memories from conversations, and create an improved version that incorporates patterns from high-quality examples.

The optimized instructions should:
1. Be clearer and more specific than the original
2. Include insights derived from the high-quality examples
3. Be well-structured with bullet points where appropriate
4. Focus on generating the most useful and meaningful memories
5. Include anything that seems to make high-quality examples stand out

Produce exactly ONE optimized instruction set that can replace the original instructions."""

        user_prompt = f"""
ORIGINAL INSTRUCTIONS:
{base_instructions}

HIGH-QUALITY EXAMPLES:
{examples_text}

Based on these examples and the original instructions, generate an improved instruction set for memory generation. 
Focus on what makes the highly-rated examples good and incorporate those insights.
"""

        # Call OpenAI for instruction optimization
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.7,
            max_tokens=1000,
        )

        # Extract optimized instructions
        optimized_instructions = response.choices[0].message.content.strip()

        print("✅ Successfully generated optimized instructions!")
        return [optimized_instructions]

    except Exception as e:
        print(f"❌ Error optimizing instructions: {e}")
        traceback.print_exc()
        return [base_instructions]  # Fallback to original instructions


def tune_prompt(min_score=MIN_QUALITY_SCORE, rounds=OPTIMIZATION_ROUNDS):
    """
    Tune the prompt using labeled examples

    Args:
        min_score: Minimum score to consider an example high quality
        rounds: Number of optimization rounds

    Returns:
        bool: True if tuning succeeded, False otherwise
    """
    # Load and prepare data
    examples = load_labeled_examples(min_score=min_score)
    if not examples:
        print("❌ No labeled examples found with sufficient quality scores.")
        return False

    print(f"🔍 Found {len(examples)} high-quality labeled examples.")

    # Extract base instructions
    base_instructions = extract_base_prompt()
    print(f"📋 Base instructions extracted ({len(base_instructions.split())} words)")

    # Create training data
    trainset = prepare_training_data(examples)

    # Optimize instructions based on high-quality examples
    optimized_instructions = optimize_instructions(base_instructions, examples)
    if not optimized_instructions:
        print("⚠️ Could not generate optimized instructions. Using original.")
        optimized_instructions = [base_instructions]

    print(f"✅ Generated {len(optimized_instructions)} optimized instruction variants")

    # Initialize program
    program = MemoryReActProgram()

    # Try different versions of DSPy API for examples
    try:
        # Basic approach: create a prompted module with manually crafted demonstration examples
        print("Using basic DSPy bootstrapping approach for examples...")

        # Extract high-quality examples (just a few)
        demonstrations = trainset[: min(3, len(trainset))]

        # Create a simple prompt with optimized instructions and examples 
        example_prompt = f"""
{optimized_instructions[0]}

Here are some example memory generations: 

{demonstrations[0].context[:300]} ...
User name: {demonstrations[0].user_name}

Interesting memories:
{', '.join([mem.get('content', str(mem)) if isinstance(mem, dict) else str(mem) for mem in demonstrations[0].interesting_memories])} 

System memories:
{', '.join([mem.get('content', str(mem)) if isinstance(mem, dict) else str(mem) for mem in demonstrations[0].system_memories])}

Now generate memories for the following conversation:
"""

        # Create output with optimized instructions and examples
        compiled_prompt = {
            "instructions": optimized_instructions[0],
            "prompt": example_prompt,
            "demonstrations": [
                {
                    "input": {"context": ex.context, "user_name": ex.user_name},
                    "output": {"interesting_memories": ex.interesting_memories, "system_memories": ex.system_memories},
                }
                for ex in demonstrations
            ],
            "original_instructions": base_instructions,
        }

        # Save optimized prompt to file
        with open(OPTIMIZED_PROMPT_PATH, "w") as f:
            json.dump(compiled_prompt, f, indent=2)

        print(f"✅ Prompt tuned successfully with {len(examples)} examples!")
        print(f"📝 Optimized prompt saved to {OPTIMIZED_PROMPT_PATH}")
        return True

    except Exception as e:
        print(f"❌ Error during prompt tuning: {e}")
        traceback.print_exc()
        return False


def apply_tuned_prompt():
    """Load and apply the tuned prompt to the memory generator"""
    if not os.path.exists(OPTIMIZED_PROMPT_PATH):
        print(f"❌ No optimized prompt found at {OPTIMIZED_PROMPT_PATH}")
        return False

    try:
        with open(OPTIMIZED_PROMPT_PATH, "r") as f:
            prompt_data = json.load(f)

        # Create a new program with the optimized prompt
        program = MemoryReActProgram()

        # Try different methods to load the prompt based on what's available
        try:
            # Check if prompt data contains a string prompt
            if "prompt" in prompt_data and isinstance(prompt_data["prompt"], str):
                # Try to use the set_prefix method if available
                if hasattr(program.react, "set_prefix"):
                    program.react.set_prefix(prompt_data["prompt"])
                # Or directly set the prompt attribute if present
                elif hasattr(program.react, "prompt"):
                    program.react.prompt = prompt_data["prompt"]
                else:
                    # Fallback to manual prompt injection through __dict__ modification
                    program.react.__dict__["prompt"] = prompt_data["prompt"]
            # If the prompt format is in DSPy's native format, try load_prompt
            elif hasattr(program.react, "load_prompt"):
                program.react.load_prompt(prompt_data)
            else:
                print("Warning: Could not determine how to apply the prompt. Using default reasoning.")

        except Exception as e:
            print(f"Warning: Error applying prompt: {e}. Using default reasoning.")
            traceback.print_exc()

        print("✅ Optimized prompt loaded successfully!")
        return program
    except Exception as e:
        print(f"❌ Error loading optimized prompt: {e}")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    tune_prompt()
