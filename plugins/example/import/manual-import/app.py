from flask import Flask, request, jsonify, send_from_directory
import requests
import json
import os
import re
import time
import openai
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# API configuration from fact.py
APP_ID = "01JPP8Y2PA2YWQPTMDAFHXWX8E"
API_KEY = "get_this_api_key_in_omi_app"
# USER_ID is now extracted dynamically from requests rather than being hardcoded
API_URL = f"https://api.omi.me/v2/integrations/{APP_ID}/user/facts"

# OpenAI API configuration
# Set your OpenAI API key in environment variables for security
# or replace with your key directly for testing purposes
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY  # Set API key directly on the module

# Configure OpenAI client with explicit parameters (avoiding proxies)
client = openai.OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=httpx.Client(
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        timeout=httpx.Timeout(timeout=30.0)
    )
)

# Maximum length for a single memory
MAX_MEMORY_LENGTH = 500  # Reduced from 2000 to 500 characters per memory

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('.', 'index.html')

def extract_memories_with_gpt(text):
    """
    Use GPT-4o to intelligently extract memories from the provided text,
    consolidating information from the same source into unified memories.
    """
    print("\n🧠 Extracting consolidated memories using GPT-4o...")
    
    try:
        # Prepare the prompt for GPT-4o with the new consolidation approach
        system_prompt = """
        You are a memory extraction specialist. Your task is to extract meaningful insights from the provided text,
        consolidating related information into coherent, contextual memories with clear attribution.

        Guidelines for extraction:
        1. Identify content blocks with clear headings/sources (like "MrBeast" or "Made to Stick")
        2. Combine bullet points and related content under these headings into SINGLE memories
        3. Begin with simple attribution phrases like: "From MrBeast: ..." or "From Made to Stick: ..."
        4. Keep the context of learnings together rather than splitting them up
        5. Be direct and specific - avoid vague or filler phrases
        6. Write in a clear, concise style - no unnecessary words
        7. Use active voice and concrete language
        8. IMPORTANT: Keep each memory UNDER 500 CHARACTERS in length

        AVOID phrases like:
        - "The user has learned that..."
        - "It appears that..."
        - "It seems like..."
        - "It's worth noting that..."
        - Any obvious filler phrases that add no value

        Example:
        Input: 
        "MrBeast
        - burn the boats
        - If you don't know smth, do it 100 times
        - Uses random word generator for ideas"

        BAD Output:
        "The user has learned from MrBeast that you need to burn the boats, if you don't know something you should first do it 100 times, and that MrBeast uses random word generators for ideas."

        GOOD Output:
        "From MrBeast: Burn the boats. Do something 100 times to learn it. Use random word generators for ideas."

        Provide 1-5 consolidated memories that capture the key insights from the input text.
        Remember to keep each memory under 500 characters and use direct, specific language.
        """
        
        user_prompt = f"Extract meaningful consolidated memories from the following text (keep each memory under 500 characters, be direct and specific):\n\n{text}"
        
        # Call the OpenAI API using the client we configured above
        response = client.chat.completions.create(
            model="gpt-4o",  # Using GPT-4o for best quality
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,  # Low temperature for more factual, consistent output
            max_tokens=2000   # Total token limit for the response
        )
        
        # Extract the response content
        memories_text = response.choices[0].message.content.strip()
        
        # Split into individual memories (each paragraph is now a consolidated memory)
        memories = [memory.strip() for memory in memories_text.split('\n\n') if memory.strip()]
        
        # Filter out any non-memories or empty lines, and truncate long memories
        processed_memories = []
        for memory in memories:
            if len(memory) < 20:  # Skip if too short
                continue
                
            # Truncate memories that are too long
            if len(memory) > MAX_MEMORY_LENGTH:
                truncated_memory = memory[:MAX_MEMORY_LENGTH-3] + "..."
                processed_memories.append(truncated_memory)
                print(f"  ⚠️ Truncated memory from {len(memory)} to {len(truncated_memory)} characters")
            else:
                processed_memories.append(memory)
        
        print(f"  ✅ GPT extracted {len(processed_memories)} consolidated memories from the text")
        for i, memory in enumerate(processed_memories):
            print(f"  📌 Memory #{i+1} ({len(memory)} chars): {memory}")
        
        return processed_memories
        
    except Exception as e:
        print(f"  ❌ Error using GPT for memory extraction: {str(e)}")
        print("  ⚠️ Falling back to rule-based extraction")
        # Fallback to the rule-based approach
        return extract_memories_consolidated(text)

def extract_memories_consolidated(text):
    """
    Rule-based extraction that consolidates related information into larger, contextual blocks
    rather than breaking everything into tiny memories.
    """
    print("\n🔍 Extracting consolidated memories using rule-based system...")
    
    # Final consolidated memories
    consolidated_memories = []
    
    # Try to identify sections with headings/titles followed by bullet points
    # This regex looks for patterns like "Title\n- point1\n- point2"
    section_pattern = re.compile(r'([^\n-]+)(?:\n\s*[-*•]\s*[^\n]+)+', re.DOTALL)
    sections = section_pattern.findall(text)
    
    for section_title in sections:
        section_title = section_title.strip()
        if not section_title:
            continue
            
        # Find all bullet points that follow this title
        # Look for the title followed by bullet points
        section_text = re.search(f"{re.escape(section_title)}((?:\n\s*[-*•][^\n]+)+)", text, re.DOTALL)
        
        if section_text:
            bullet_points = re.findall(r'[-*•]\s*([^\n]+)', section_text.group(1))
            
            if bullet_points:
                # Create a consolidated memory with source attribution
                memory_start = f"From {section_title}: "
                
                # Start with the first bullet point
                current_memory = memory_start + bullet_points[0].strip()
                
                # Try to add more bullet points up to the maximum length
                for i, point in enumerate(bullet_points[1:], start=1):
                    point_text = point.strip()
                    
                    # Check if adding this point would exceed the maximum length
                    connector = ". "
                    if len(current_memory + connector + point_text) <= MAX_MEMORY_LENGTH:
                        current_memory += connector + point_text
                    else:
                        # This point would make the memory too long, so save the current memory
                        # and start a new one with the same title
                        consolidated_memories.append(current_memory)
                        print(f"  📌 Extracted consolidated memory from section '{section_title}' (part {len(consolidated_memories)})")
                        current_memory = f"{memory_start}{point_text}"
                
                # Add the final memory if not empty
                if current_memory:
                    consolidated_memories.append(current_memory)
                    print(f"  📌 Extracted consolidated memory from section '{section_title}' (part {len(consolidated_memories)})")
    
    # If no structured sections were found, try to extract paragraphs
    if not consolidated_memories:
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        for paragraph in paragraphs:
            # Skip if too short
            if len(paragraph) < 50:
                continue
                
            # Split longer paragraphs if needed
            if len(paragraph) > MAX_MEMORY_LENGTH:
                chunks = [paragraph[i:i+MAX_MEMORY_LENGTH] for i in range(0, len(paragraph), MAX_MEMORY_LENGTH)]
                for i, chunk in enumerate(chunks):
                    consolidated_memories.append(chunk)
                    print(f"  📌 Extracted paragraph chunk {i+1} as memory: {chunk[:50]}...")
            else:
                consolidated_memories.append(paragraph)
                print(f"  📌 Extracted paragraph as memory: {paragraph[:50]}...")
    
    # As a last resort, if nothing else was found, just return the whole text as one memory
    if not consolidated_memories and len(text.strip()) > 0:
        # Split into reasonable chunks
        chunks = [text[i:i+MAX_MEMORY_LENGTH] for i in range(0, len(text), MAX_MEMORY_LENGTH)]
        for chunk in chunks:
            consolidated_memories.append(chunk)
            print(f"  📌 Added text chunk as memory: {chunk[:50]}...")
    
    # Print character count for each memory
    for i, memory in enumerate(consolidated_memories):
        print(f"  📏 Memory #{i+1} length: {len(memory)} characters")
    
    print(f"  ✅ Extracted {len(consolidated_memories)} consolidated memories using rule-based extraction")
    return consolidated_memories

@app.route('/submit-memories', methods=['POST'])
def submit_memories():
    """Process and submit memories to the OMI API"""
    try:
        start_time = time.time()
        
        # Get the text from the request
        data = request.json
        raw_memories = data.get('memories', [])
        
        # Extract user_id from request
        user_id = data.get('uid')
        
        if not user_id:
            print("❌ ERROR: No user ID provided")
            return jsonify({"success": False, "error": "No user ID provided. Please include 'uid' in your request."}), 400
        
        if not raw_memories:
            print("❌ ERROR: No content provided")
            return jsonify({"success": False, "error": "No content provided"}), 400
        
        # Check if OpenAI API key is set
        use_ai = data.get('use_ai', True)  # Default to True
        ai_available = OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here"
        
        # Process the raw text
        all_memories = []
        for raw_memory in raw_memories:
            # Use GPT-4o for more intelligent extraction if enabled and available
            if use_ai and ai_available:
                extracted = extract_memories_with_gpt(raw_memory)
                all_memories.extend(extracted)
            else:
                # If GPT is not available or not requested, fall back to rule-based extraction
                if not ai_available and use_ai:
                    print("⚠️ OpenAI API key not configured. Falling back to rule-based extraction.")
                
                # Use consolidated extraction for all text
                extracted = extract_memories_consolidated(raw_memory)
                all_memories.extend(extracted)
        
        # Process each memory
        results = []
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        print("\n" + "="*50)
        print(f"📝 Processing {len(all_memories)} consolidated memories for user {user_id}...")
        print("="*50)
        
        memory_count = 0
        success_count = 0
        error_count = 0
        
        for memory in all_memories:
            memory_count += 1
            
            # Skip empty memories
            if not memory or len(memory) < 20:  # Minimum length for a memory
                continue
            
            # Ensure memories are within the maximum length
            if len(memory) > MAX_MEMORY_LENGTH:
                memory = memory[:MAX_MEMORY_LENGTH-3] + "..."
                print(f"⚠️ Truncated memory to {MAX_MEMORY_LENGTH} characters")
            
            # Print the full memory with no truncation
            print(f"\n🔍 MEMORY #{memory_count} ({len(memory)} chars): {memory}")
            
            # Create the facts data according to existing structure (API still uses "facts")
            memory_data = {
                "text": memory,
                "text_source": "other",
                "text_source_spec": "learning_notes"
            }
            
            # Print full request data without truncation
            print(f"📤 Request data: {json.dumps(memory_data, indent=2)}")
            
            # Implement simple rate limiting
            if memory_count > 1:
                time.sleep(0.5)  # Half second delay between requests
            
            # Send the request to OMI API with dynamic user_id (still using the facts endpoint)
            response = requests.post(
                f"{API_URL}?uid={user_id}",
                headers=headers,
                data=json.dumps(memory_data)
            )
            
            # Record result
            result = {
                "memory": memory,  # Changed from "fact" to "memory"
                "status_code": response.status_code,
                "success": response.status_code == 200
            }
            
            if response.status_code == 200:
                success_count += 1
                print(f"✅ SUCCESS: Status code {response.status_code}")
                try:
                    if response.text:
                        response_json = response.json()
                        print(f"📥 Response: {json.dumps(response_json, indent=2)}")
                    else:
                        print("📥 Response: Empty response body (success)")
                except:
                    print(f"📥 Response: {response.text}")
            else:
                error_count += 1
                print(f"❌ ERROR: Status code {response.status_code}")
                print(f"📥 Response: {response.text}")
                result["error"] = response.text
            
            results.append(result)
        
        # Check if all memories were successful
        all_success = error_count == 0
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        print("\n" + "="*50)
        print(f"📊 SUMMARY: Processed {len(all_memories)} consolidated memories for user {user_id}. {success_count} succeeded, {error_count} failed.")
        print(f"⏱️ Total processing time: {processing_time:.2f} seconds")
        print("="*50 + "\n")
        
        return jsonify({
            "success": all_success,
            "results": results,
            "message": f"Processed {len(all_memories)} consolidated memories. {success_count} succeeded, {error_count} failed.",
            "processing_time": f"{processing_time:.2f} seconds",
            "ai_used": use_ai and ai_available
        })
    
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    print(f"🚀 Starting Memories Collector server...")
    print(f"📡 API URL: {API_URL}")
    print(f"⚙️ App ID: {APP_ID}")
    print(f"👤 User ID: Dynamic (extracted from URL)")
    
    # Check if OpenAI API is configured
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        print(f"🧠 GPT-4o extraction: ENABLED")
    else:
        print(f"🧠 GPT-4o extraction: DISABLED (API key not set)")
        print(f"   Set the OPENAI_API_KEY environment variable or update the key in the code")
    
    print(f"💻 Server running at: http://localhost:5001")
    print(f"💡 Access with: http://localhost:5001/?uid=YOUR_USER_ID")
    print("="*50)
    print("Submit memories through the web interface and watch responses here!")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5001, debug=True) 