from flask import Flask, request, jsonify, send_from_directory
import requests
import json
import os
import re
import time
import openai
import httpx
from dotenv import load_dotenv
import trafilatura

# Load environment variables from .env file
load_dotenv()

# Add this near the top with other imports
from flask_cors import CORS

# After creating the Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# API configuration from fact.py
APP_ID = "01JW1J54TSCC101VT7SEZFSAQP"
API_KEY = "sk_5b307a8bf6759da55742e97b10529a8d"
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
        section_text = re.search(f"{re.escape(section_title)}{r'((?:\n\s*[-*•][^\n]+)+)'}", text, re.DOTALL)
        
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
                "text_source": "other",  # Changed from "url" to "other" to match API requirements
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

@app.route('/extract-from-url', methods=['POST'])
def extract_from_url():
    """Extract content from a URL using Trafilatura and process it"""
    try:
        # Get the URL from the request
        data = request.json
        url = data.get('url', '')
        user_id = data.get('uid')
        
        if not url:
            return jsonify({"success": False, "error": "No URL provided"}), 400
            
        if not user_id:
            return jsonify({"success": False, "error": "No user ID provided"}), 400
        
        print(f"\n🌐 Extracting content from URL: {url}")
        
        # Download and extract the main content from the URL using Trafilatura
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded is None:
                return jsonify({"success": False, "error": "Failed to download content from URL"}), 400
                
            # Extract the main text content
            extracted_text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
            
            if not extracted_text or len(extracted_text.strip()) < 50:
                return jsonify({"success": False, "error": "No significant content could be extracted from the URL"}), 400
                
            print(f"✅ Successfully extracted {len(extracted_text)} characters from URL")
            
            # Now process this text through the existing memory extraction pipeline
            # Check if OpenAI API key is set
            use_ai = data.get('use_ai', True)  # Default to True
            ai_available = OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here"
            
            # Process the extracted text
            if use_ai and ai_available:
                memories = extract_memories_with_gpt(extracted_text)
            else:
                if not ai_available and use_ai:
                    print("⚠️ OpenAI API key not configured. Falling back to rule-based extraction.")
                memories = extract_memories_consolidated(extracted_text)
            
            # Process each memory - reusing code from submit_memories route
            results = []
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
            
            print("\n" + "="*50)
            print(f"📝 Processing {len(memories)} consolidated memories from URL for user {user_id}...")
            print("="*50)
            
            memory_count = 0
            success_count = 0
            error_count = 0
            
            for memory in memories:
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
                    "text_source": "other",  # Changed from "url" to "other" to match API requirements
                    "text_source_spec": url
                }
                
                # Print full request data without truncation
                print(f"📤 Request data: {json.dumps(memory_data, indent=2)}")
                
                # Implement simple rate limiting
                if memory_count > 1:
                    time.sleep(0.5)  # Half second delay between requests
                
                # Send the request to OMI API with dynamic user_id
                response = requests.post(
                    f"{API_URL}?uid={user_id}",
                    headers=headers,
                    data=json.dumps(memory_data)
                )
                
                # Record result
                result = {
                    "memory": memory,
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
            
            return jsonify({
                "success": all_success,
                "results": results,
                "message": f"Processed {len(memories)} consolidated memories from URL. {success_count} succeeded, {error_count} failed.",
                "source_url": url,
                "ai_used": use_ai and ai_available
            })
            
        except Exception as e:
            print(f"❌ Error extracting content from URL: {str(e)}")
            return jsonify({"success": False, "error": f"Error extracting content: {str(e)}"}), 500
    
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/extract-from-instagram', methods=['POST'])
def extract_from_instagram():
    """Extract content from an Instagram profile and process it"""
    try:
        # Get the username from the request
        data = request.json
        username = data.get('username', '')
        
        # Remove '@' symbol if present
        if username.startswith('@'):
            username = username[1:]
            
        user_id = data.get('uid')
        extract_posts = data.get('extract_posts', False)
        
        if not username:
            return jsonify({"success": False, "error": "No Instagram username provided"}), 400
            
        if not user_id:
            return jsonify({"success": False, "error": "No user ID provided"}), 400
        
        print(f"\n📱 Extracting content from Instagram profile: {username}")
        
        # Set up the Instagram API client
        instagram_client = httpx.Client(
            headers={
                # Internal ID of Instagram backend app
                "x-ig-app-id": "936619743392459",
                # Browser-like headers
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
            }
        )
        
        # Fetch the Instagram profile data
        try:
            result = instagram_client.get(
                f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                timeout=10.0
            )
            
            if result.status_code != 200:
                return jsonify({"success": False, "error": f"Failed to fetch Instagram profile: HTTP {result.status_code}"}), 400
                
            data = result.json()
            user_data = data.get("data", {}).get("user", {})
            
            if not user_data:
                return jsonify({"success": False, "error": "No user data found"}), 400
                
            # Extract relevant information
            profile_info = {
                "username": user_data.get("username"),
                "full_name": user_data.get("full_name"),
                "biography": user_data.get("biography"),
                "followers": user_data.get("edge_followed_by", {}).get("count"),
                "following": user_data.get("edge_follow", {}).get("count"),
                "is_verified": user_data.get("is_verified"),
                "profile_pic_url": user_data.get("profile_pic_url"),
                "external_url": user_data.get("external_url")
            }
            
            # Extract posts if requested
            posts = None
            if extract_posts:
                try:
                    print(f"📸 Extracting posts for Instagram profile: {username}")
                    
                    # Get recent posts from the profile data
                    recent_posts = user_data.get("edge_owner_to_timeline_media", {}).get("edges", [])
                    posts = []
                    
                    # Extract basic post info from profile data
                    for post_edge in recent_posts:
                        post_node = post_edge.get("node", {})
                        shortcode = post_node.get("shortcode")
                        
                        if shortcode:
                            try:
                                # Use GraphQL to get detailed post data
                                post_data = scrape_post(shortcode, instagram_client)
                                posts.append(post_data)
                                print(f"✅ Extracted post {shortcode}")
                            except Exception as e:
                                print(f"⚠️ Error extracting post {shortcode}: {str(e)}")
                                # Add basic info if GraphQL fails
                                posts.append({
                                    "shortcode": shortcode,
                                    "display_url": post_node.get("display_url"),
                                    "caption": post_node.get("edge_media_to_caption", {}).get("edges", [{}])[0].get("node", {}).get("text", ""),
                                    "likes": post_node.get("edge_liked_by", {}).get("count"),
                                    "comments": post_node.get("edge_media_to_comment", {}).get("count"),
                                    "timestamp": post_node.get("taken_at_timestamp"),
                                    "error": str(e)
                                })
                    
                    print(f"📊 Extracted {len(posts)} posts from Instagram profile")
                except Exception as e:
                    print(f"⚠️ Error extracting posts: {str(e)}")
            
            # Format the profile information in a human-friendly way
            formatted_text = f"Instagram Profile: {profile_info['full_name']} (@{profile_info['username']})\n\n"
            formatted_text += f"Bio: {profile_info['biography']}\n\n"
            formatted_text += f"Followers: {profile_info['followers']:,}\n"
            formatted_text += f"Following: {profile_info['following']:,}\n"
            formatted_text += f"Verified: {'Yes' if profile_info['is_verified'] else 'No'}\n"
            
            if profile_info['external_url']:
                formatted_text += f"Website: {profile_info['external_url']}\n"
            
            # Add post information to the formatted text if available
            if posts and len(posts) > 0:
                formatted_text += f"\nRecent Posts: {len(posts)}\n"
                for i, post in enumerate(posts[:3], 1):  # Show info for first 3 posts
                    caption = post.get("caption", "") or ""
                    if len(caption) > 100:
                        caption = caption[:97] + "..."
                    formatted_text += f"\nPost {i}: {caption}\n"
            
            # Check if OpenAI API key is set
            use_ai = data.get('use_ai', True)  # Default to True
            ai_available = OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here"
            
            # Process the formatted text through GPT-4 to make it more human-friendly
            if use_ai and ai_available:
                try:
                    system_prompt = """
                    You are a helpful assistant that formats Instagram profile information in a natural, 
                    human-friendly way. Present the information conversationally as if you're describing 
                    the profile to someone interested in learning about it. Don't use JSON or structured 
                    formats - use natural language paragraphs.
                    """
                    
                    user_prompt = f"Format this Instagram profile information in a natural, conversational way:\n\n{formatted_text}"
                    
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=1000
                    )
                    
                    formatted_text = response.choices[0].message.content.strip()
                    print(f"✅ Successfully formatted Instagram profile with GPT-4o")
                    
                except Exception as e:
                    print(f"⚠️ Error using GPT for formatting: {str(e)}")
                    # Continue with the basic formatted text if GPT fails
            
            # Create a single memory with the formatted text
            memory = formatted_text
            
            # Process the memory - reusing code from submit_memories route
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
            
            # Create the facts data according to existing structure
            memory_data = {
                "text": memory,
                "text_source": "other",  # Using "other" instead of "instagram" to comply with API
                "text_source_spec": f"instagram_profile_{username}"
            }
            
            # Print full request data
            print(f"📤 Request data: {json.dumps(memory_data, indent=2)}")
            
            # Send the request to OMI API with dynamic user_id
            response = requests.post(
                f"{API_URL}?uid={user_id}",
                headers=headers,
                data=json.dumps(memory_data)
            )
            
            # Record result
            result = {
                "memory": memory,
                "status_code": response.status_code,
                "success": response.status_code == 200
            }
            
            if response.status_code == 200:
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
                print(f"❌ ERROR: Status code {response.status_code}")
                print(f"📥 Response: {response.text}")
                result["error"] = response.text
            
            response_data = {
                "success": result["success"],
                "results": [result],
                "message": f"Processed Instagram profile for @{username}.",
                "profile_info": profile_info,
                "ai_used": use_ai and ai_available
            }
            
            # Add posts to response if available
            if posts is not None:
                response_data["posts"] = posts
                
            return jsonify(response_data)
            
        except Exception as e:
            print(f"❌ Error extracting content from Instagram: {str(e)}")
            return jsonify({"success": False, "error": f"Error extracting content: {str(e)}"}), 500
    
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500

# Helper function to scrape Instagram post data using GraphQL
def scrape_post(shortcode, client=None):
    """Scrape single Instagram post data using GraphQL"""
    print(f"Scraping Instagram post: {shortcode}")
    
    # Instagram GraphQL constants
    INSTAGRAM_DOCUMENT_ID = "8845758582119845"  # constant ID for post documents on instagram.com
    
    # Prepare GraphQL variables
    variables = {
        'shortcode': shortcode,
        'fetch_tagged_user_count': None,
        'hoisted_comment_id': None,
        'hoisted_reply_id': None
    }
    
    # URL encode the variables
    from urllib.parse import quote
    variables_encoded = quote(json.dumps(variables, separators=(',', ':')))
    body = f"variables={variables_encoded}&doc_id={INSTAGRAM_DOCUMENT_ID}"
    
    # Create a new client if one wasn't provided
    if client is None:
        client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "content-type": "application/x-www-form-urlencoded"
            }
        )
    
    # Make the GraphQL request
    result = client.post(
        url="https://www.instagram.com/graphql/query",
        headers={"content-type": "application/x-www-form-urlencoded"},
        data=body,
        timeout=15.0
    )
    
    # Parse the response
    if result.status_code != 200:
        raise Exception(f"Failed to fetch post data: HTTP {result.status_code}")
    
    data = result.json()
    
    # Check for errors in the response
    if "errors" in data:
        error_msg = data.get("errors", [{}])[0].get("message", "Unknown error")
        raise Exception(f"GraphQL error: {error_msg}")
    
    # Extract the post data
    post_data = data.get("data", {}).get("xdt_shortcode_media", {})
    
    if not post_data:
        raise Exception("No post data found in response")
    
    # Parse the post data to extract relevant fields
    parsed_post = parse_post(post_data)
    return parsed_post

# Helper function to parse Instagram post data
def parse_post(data):
    """Parse Instagram post data to extract relevant fields"""
    # Basic parsing without jmespath dependency
    try:
        # Extract basic post information
        parsed = {
            "id": data.get("id"),
            "shortcode": data.get("shortcode"),
            "display_url": data.get("display_url"),
            "is_video": data.get("is_video", False),
            "taken_at": data.get("taken_at_timestamp"),
            "likes": data.get("edge_media_preview_like", {}).get("count"),
            "location": data.get("location", {}).get("name") if data.get("location") else None,
        }
        
        # Extract caption
        caption_edges = data.get("edge_media_to_caption", {}).get("edges", [])
        if caption_edges and len(caption_edges) > 0:
            parsed["caption"] = caption_edges[0].get("node", {}).get("text")
        else:
            parsed["caption"] = ""
        
        # Extract comments count
        parsed["comments_count"] = data.get("edge_media_to_parent_comment", {}).get("count", 0)
        
        # Extract video URL if it's a video
        if parsed["is_video"]:
            parsed["video_url"] = data.get("video_url")
            parsed["video_view_count"] = data.get("video_view_count")
            parsed["video_play_count"] = data.get("video_play_count")
            parsed["video_duration"] = data.get("video_duration")
        
        # Extract tagged users
        tagged_users = []
        tagged_edges = data.get("edge_media_to_tagged_user", {}).get("edges", [])
        for edge in tagged_edges:
            username = edge.get("node", {}).get("user", {}).get("username")
            if username:
                tagged_users.append(username)
        parsed["tagged_users"] = tagged_users
        
        # Extract comments (limited to avoid large responses)
        comments = []
        comment_edges = data.get("edge_media_to_parent_comment", {}).get("edges", [])
        for edge in comment_edges[:5]:  # Limit to first 5 comments
            node = edge.get("node", {})
            comment = {
                "id": node.get("id"),
                "text": node.get("text"),
                "created_at": node.get("created_at"),
                "owner": node.get("owner", {}).get("username"),
                "likes": node.get("edge_liked_by", {}).get("count", 0)
            }
            comments.append(comment)
        parsed["comments"] = comments
        
        return parsed
    except Exception as e:
        print(f"Error parsing post data: {str(e)}")
        # Return basic data if parsing fails
        return {
            "shortcode": data.get("shortcode"),
            "display_url": data.get("display_url"),
            "error": f"Error parsing post data: {str(e)}"
        }

# Remove the duplicate blocks and replace with this at the end of the file

# For local development only
if __name__ == "__main__":
    # Use this for local development
    app.run(debug=True, host='0.0.0.0', port=5001)
    
# For production with Vercel, we don't need to call app.run()
# Vercel will use the 'app' variable directly