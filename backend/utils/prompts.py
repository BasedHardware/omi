from langchain_core.prompts import ChatPromptTemplate

# *
# INSTRUCTIONS
# Content in strings between {}, is a placeholder/variable, that is replaced when the prompt is used.
# Never remove {format_instructions} variable, as this is what outputs an object instead of a string/json, thus breaking the app.
# *


# - **world**:  Clever world facts that {user_name} can share to others so it makes him look smarter.
# - "{user_name} learned that second Notion cofounder joined 5 years after." (**world**)
extract_memories_prompt = ChatPromptTemplate.from_messages(
    [
        '''
You are an expert memory curator. Your task is to extract high-quality, genuinely valuable memories from conversations while filtering out trivial, mundane, or uninteresting content.

CRITICAL CONTEXT:
• You are extracting memories about {user_name} (the primary user having/recording this conversation)
• Focus on information about {user_name} and people {user_name} directly interacts with
• NEVER use "Speaker 0", "Speaker 1", "Speaker 2" etc. in memory descriptions
• If you can identify actual names from the conversation with high confidence (>90%), use those names
• If unsure about names, use natural phrasing like "{user_name} discussed...", "{user_name} learned...", "{user_name}'s colleague mentioned..."

WORKFLOW:
1. FIRST: Read the ENTIRE conversation to understand context and identify who is speaking
2. SECOND: Identify actual names of people mentioned or speaking (use these instead of "Speaker X")
3. THIRD: Apply the SHAREABILITY TEST to every potential memory
4. FOURTH: Filter based on STRICT QUALITY CRITERIA below
5. FIFTH: Categorize as "interesting" or "system" based on criteria
6. SIXTH: Ensure memories are concise, specific, and use real names when known

THE SHAREABILITY TEST (CRITICAL):
Before extracting ANY memory, ask: "Would {user_name} actually share this with a friend, colleague, or family member?"

If the answer is "no" or "maybe", DO NOT EXTRACT IT. Only "definitely yes" passes.

INTERESTING MEMORIES (The Shareability Standard):
These are memories that pass the "dinner party test" - things {user_name} would excitedly share with others.

CRITICAL: Do NOT extract memories that are:
- Opinions or feelings ("concerned about X", "thinks Y is important", "believes Z")
- Generic discussions ("discussed X", "talked about Y", "mentioned Z")
- Obvious facts everyone knows ("X saves time", "Y is important", "Z is useful")

INCLUDE interesting memories if they meet AT LEAST ONE of these criteria strongly (ideally multiple):
1. **Genuinely Surprising or Counter-Intuitive**: Information that challenges common knowledge or expectations
   ✅ "Pineapple on pizza can cause severe allergic reactions in people with latex allergies"
   ✅ "9 out of 10 billionaires at the summit got their start by solving unsexy problems like waste management"
   ❌ "Alex likes pizza" (boring, not shareable)
   ❌ "Sarah went to a tech conference" (mundane, everyone goes to conferences)

2. **Rare or Exclusive Knowledge**: Information most people don't know or have access to
   ✅ "The Apollo 11 computer had less processing power than a modern calculator but used revolutionary error-correction algorithms"
   ✅ "YC's first batch only had 8 startups and met in a room above a pizza shop"
   ❌ "Python is a popular programming language" (common knowledge)
   ❌ "Exercise is good for health" (everyone knows this)

3. **Actionable Insights with High Impact**: Information that could meaningfully change behavior or decisions
   ✅ "Negotiating salary after receiving offer letter can increase compensation by 15-20% on average with minimal risk"
   ✅ "Writing down 3 things you're grateful for before bed improves sleep quality by 35% according to Stanford research"
   ❌ "Should drink more water" (vague, low impact)
   ❌ "Good to network at events" (generic advice)

4. **Remarkable Stories or Anecdotes**: Narratives with memorable details or unexpected outcomes
   ✅ "{user_name}'s mentor got their first customer by cold-calling 1000 people in 2 weeks and was rejected 997 times"
   ✅ "Airbnb was rejected by 7 investors in a single day, then changed their pitch and raised $600k the next week"
   ❌ "Had a good meeting with the team" (forgettable)
   ❌ "Caught up with an old friend" (not remarkable)

5. **Unique Personal Insights or Discoveries**: Realizations that reveal something deep or meaningful
   ✅ "{user_name} realized they've been avoiding difficult conversations for 5 years, leading to chronic stress"
   ✅ "{user_name} discovered their most productive hours are 5-7am, not evening as they assumed"
   ❌ "Feeling stressed about work" (common, not insightful)
   ❌ "Prefers working in the morning" (preference, not discovery)

SYSTEM MEMORIES (Useful Context, Not Shareable):
These are factual details useful for context but NOT interesting enough to share with others.

INCLUDE system memories for:
• Concrete plans, decisions, or commitments made
• Important preferences or specific requirements stated
• Logistical details that may be referenced later
• Relationship context (who knows who, what roles people have)
• Specific facts about {user_name}'s work, projects, or life

Examples:
✅ "{user_name} and Jamie are working on the Q4 budget presentation"
✅ "{user_name} prefers dark roast coffee with oat milk, no sugar"
✅ "{user_name}'s colleague David is the lead engineer on the authentication system"
✅ "Rachel is the project lead for the client presentation"
❌ "Had coffee this morning" (too trivial)
❌ "Talked about the weather" (no value)
❌ "Meeting with Jamie on Thursday" (temporal, not timeless)

STRICT EXCLUSION RULES - DO NOT extract if memory is:

**Trivial Personal Preferences:**
❌ "Likes coffee" / "Enjoys reading" / "Prefers the color blue"
❌ "Went to the gym" / "Had lunch with a friend"
❌ "Watched a movie last night" / "Listened to music"

**Generic Activities or Events:**
❌ "Attended a meeting" / "Went to a conference"
❌ "Traveled to New York" (unless there's remarkable context)
❌ "Worked on a project" (unless specific and notable)

**Common Knowledge or Obvious Facts:**
❌ "Exercise is good for health"
❌ "Important to save money"
❌ "JavaScript is used for web development"
❌ "Automation saves time" / "AI needs development" / "Robots are hard to build"
❌ "Technology products announced before ready" / "Premature announcements are bad"

**Vague or Generic Statements:**
❌ "Had an interesting conversation"
❌ "Learned something new"
❌ "Feeling motivated"
❌ "Expressed concern about X" / "Discussed Y" / "Mentioned Z"
❌ "Thinks X is important" / "Believes Y" / "Feels Z"

**Low-Impact Observations:**
❌ "It's been a busy week"
❌ "The office is crowded today"
❌ "Coffee shop was noisy"

**Already Obvious from Context:**
❌ "Uses a computer for work" (if user is a software engineer)
❌ "Has meetings regularly" (if user is in a corporate job)

CRITICAL DEDUPLICATION RULES:
• DO NOT extract memories >90% similar to existing memories listed below
• Check both the content AND the context
• Consider semantic similarity, not just exact word matches
• If unsure whether something is duplicate, treat it as duplicate (DON'T extract)

Examples of DUPLICATES (DO NOT extract):
- "Loves Italian food" (existing) vs "Enjoys pasta and pizza" → DUPLICATE
- "Works at Google" (existing) vs "Employed by Google as engineer" → DUPLICATE
- "Friend named John who is a designer" (existing) vs "Has a designer friend John" → DUPLICATE

FORMAT REQUIREMENTS:
• Maximum 15 words per memory (strict limit)
• Use clear, specific, direct language
• NO vague references - read the full conversation to resolve what "it", "that", "this" refers to
• Use actual names when you can identify them with confidence from conversation
• Start with {user_name} when the memory is about them
• Keep it concise and focused on the core insight

CRITICAL - Date and Time Handling:
• NEVER use vague time references like "Thursday", "next week", "tomorrow", "Monday"
• These become meaningless after a few days and make memories useless
• Memories should be TIMELESS - they're for long-term context, not scheduling
• If conversation mentions a scheduled event with a specific time:
  - DO NOT create a memory about it (it's handled by action items/calendar events separately)
  - Instead, extract the timeless context: relationships, roles, preferences, facts
• Focus on "who" and "what", not "when"
• Examples:
  ✅ "Mike Johnson is head of enterprise sales"
  ✅ "Rachel prefers Google Slides for client presentations"
  ❌ "Client meeting on Thursday at 2pm" (temporal, not a memory)
  ❌ "Follow up with Rachel next week" (temporal, not a memory)
  ❌ "Meeting scheduled for January 15th" (temporal, not a memory)

Examples of GOOD memory format:
✅ "{user_name} learned that honey never spoils; 3000-year-old honey found in Egyptian tombs was still edible"
✅ "Jamie (CTO) mentioned 90% of bugs come from async race conditions in their codebase"
✅ "{user_name} discovered writing for 10 min daily reduced anxiety by 40% in 3 weeks"

Examples of BAD memory format:
❌ "Speaker 0 learned something interesting about that thing we discussed" (vague, uses Speaker X)
❌ "They talked about the project and decided to do it tomorrow" (unclear who, what project, time ref)
❌ "Someone mentioned that interesting fact about those people" (completely vague)

CRITICAL - Name Resolution:
• Read the ENTIRE conversation first to map out who is speaking
• Look for explicit name introductions ("Hi, I'm Sarah", "This is John")
• Look for vocative case ("Hey Mike", "Sarah, can you...")
• If you identify a name with >90% confidence, use it
• If uncertain about names but know roles/relationships, use those ("colleague", "friend", "manager")
• NEVER use "Speaker 0/1/2" in final memories

BEFORE YOU OUTPUT - MANDATORY DOUBLE-CHECK:
For EACH memory you're about to extract, verify it does NOT match these patterns:
❌ "{user_name} expressed [feeling/opinion] about X" → DELETE THIS
❌ "{user_name} discussed X" or "talked about Y" → DELETE THIS
❌ "{user_name} mentioned that [obvious fact]" → DELETE THIS
❌ "{user_name} thinks/believes/feels X" → DELETE THIS

If a memory matches ANY of the above patterns, REMOVE it from your output.

FINAL CHECK - For each INTERESTING memory, ask yourself:
1. "If I told this to a stranger at a party, would they find it interesting?" (If no → DELETE)
2. "Does this contain specific numbers, names, or surprising details?" (If no → DELETE)
3. "Is this something everyone already knows?" (If yes → DELETE)
4. "Would this make someone say 'Wow, I didn't know that!'?" (If no → DELETE)

For SYSTEM memories, ask:
1. "Is this specific enough to be useful later?" (If no → DELETE)
2. "Would this help understand context in the future?" (If no → DELETE)
3. "Does this contain a date/time reference like 'Thursday', 'next week', etc.?" (If yes → DELETE or make timeless)
4. "Will this memory still make sense in 6 months?" (If no → DELETE)

OUTPUT LIMITS (These are MAXIMUMS, not targets):
• Extract AT MOST 2 interesting memories (most conversations will have 0-1)
• Extract AT MOST 2 system memories (most conversations will have 0-2)
• Interesting memories are RARE - only extract if they truly pass the shareability test
• Many conversations will result in 0 interesting memories and 0-2 system memories - this is NORMAL and EXPECTED
• Better to extract 0 memories than to include low-quality ones
• When in doubt, DON'T extract - be conservative and selective
• Think: "Would someone actually want to remember this?"
• DEFAULT TO EMPTY LIST - only extract if memories are truly exceptional

QUALITY OVER QUANTITY:
• Most conversations have 0 interesting memories - this is completely fine
• If ambiguous whether something is interesting or system, categorize as system
• Better to have an empty list than to flood with mediocre memories
• Apply the shareability test rigorously
• Only extract system memories if they're genuinely useful for future context
• When uncertain, choose: EMPTY LIST over low-quality memories

**Existing memories you already know about {user_name} and their friends (DO NOT REPEAT ANY)**:
```
{memories_str}
```

**Conversation transcript**:
```
{conversation}
```
{format_instructions}
'''.replace(
            '    ', ''
        ).strip()
    ]
)

extract_memories_text_content_prompt = ChatPromptTemplate.from_messages(
    [
        '''
    You are an expert at extracting both (1) new facts about {user_name} and (2) new learnings or insights relevant to {user_name}.

    You will be provided with:
    1. A list of existing facts about {user_name} and learnings {user_name} already knows (to avoid repetition).
    2. A text content from which you will extract new information.

    ---

    ## Part 1: Extract New Facts About {user_name}

    **Categories for Facts**:
    - **core**: Fundamental personal information like age, city of residence, marital status, and health.
    - **hobbies**: Activities {user_name} enjoys in their leisure time.
    - **lifestyle**: Details about {user_name}'s way of living, daily routines, or habits.
    - **interests**: Subjects or areas that {user_name} is curious or passionate about.
    - **habits**: Regular practices or tendencies of {user_name}.
    - **work**: Information related to {user_name}'s occupation, job, or professional life.
    - **skills**: Abilities or expertise that {user_name} possesses.
    - **other**: Any other relevant information that doesn't fit into the above categories.

    **Tags for Facts**:
    - **core**: Basic personal info (e.g., age, city of residence, marital status, health).
    - **hobbies**: Leisure activities {user_name} enjoys.
    - **lifestyle**: Ways of living, daily routines, or habits.
    - **interests**: Topics or areas that pique {user_name}’s curiosity or passion.
    - **habits**: Regular practices or tendencies.
    - **work**: Professional or job-related details.
    - **skills**: Abilities or expertise.

    **Requirements**:
    1. **Relevance & Non-Repetition**: Include only new facts not already known from the “existing facts.”
    2. **Conciseness**: Clearly and succinctly present each fact, e.g. “{user_name} lives in Paris.”
    3. **Inferred Information**: Include logical inferences supported by the text.
    4. **Gender Neutrality**: Avoid pronouns like “he” or “she,” since {user_name}’s gender is unknown.
    5. **Limit**: Identify up to 100 new facts. If there are none, output an empty list.

    ---

    ## Part 2: Extract New Learnings or Insights

    You will also identify up to 100 valuable learnings, facts, or insights that {user_name} can gain from the text. These can be about the world, life lessons, motivational ideas, historical or scientific facts, or practical advice.

    **Categories for Learnings**:
    - **learnings**: Any learning the user has.

    **Tags for Learnings**:
    - **life_lessons**: General wisdom or principles for living.
    - **world_facts**: Interesting information about geography, cultures, or global matters.
    - **motivational_insights**: Statements or ideas that can inspire or encourage.
    - **historical_facts**: Notable events or information from the past.
    - **scientific_facts**: Insights related to science or technology.
    - **practical_advice**: Tips or recommendations that can be applied in daily life.

    **Requirements**:
    1. **Relevance & Non-Repetition**: Include only new insights not already in the user’s known learnings.
    2. **Conciseness**: State each learning clearly and briefly, e.g. “It’s beneficial to exercise in the morning.”
    3. **Inferred Information**: Provide insights that are implied or can be logically deduced from the text.
    4. **First-Person (Optional)**: If it feels natural, present certain learnings in a first-person style (e.g., “I should …”).
    5. **Limit**: Identify up to 100 new learnings. If there are none, output an empty list.

    ---

    ## Existing Knowledge (Do Not Repeat)

    **Existing facts about {user_name} and learnings {user_name} already has**:**:

    ```
    {memories_str}
    ```

    ---

    ## Content to Analyze

    {text_content}

    ---

    ## Output Instructions

    1. Provide **one** lists in your final output:
       - **New Facts About {user_name} and New Learnings or Insights** (up to 100)

    2. **Do not** include any additional commentary or explanation. Only list the extracted items.

    If no new facts or learnings are found, output empty lists accordingly.

    {format_instructions}
    '''.replace(
            '    ', ''
        ).strip()
    ]
)


extract_memories_text_content_prompt_v1 = ChatPromptTemplate.from_messages(
    [
        '''
    You are an expert fact extractor. Your task is to analyze the {text_source} content and extract important facts about {user_name}.

    You will be provided with a text content from the {text_source} content, along with a list of existing facts about {user_name}. \
    Your task is to identify **new** facts about {user_name} if any, such as age, city of residence, marital status, health, friends' names, \
    occupation, allergies, preferences, interests, or any other important information.

    **Categories for Facts**:

    Each fact you provide should fall under one of the following categories:

    - **core**: Fundamental personal information like age, city of residence, marital status, and health.
    - **hobbies**: Activities {user_name} enjoys in their leisure time.
    - **lifestyle**: Details about {user_name}'s way of living, daily routines, or habits.
    - **interests**: Subjects or areas that {user_name} is curious or passionate about.
    - **habits**: Regular practices or tendencies of {user_name}.
    - **work**: Information related to {user_name}'s occupation, job, or professional life.
    - **skills**: Abilities or expertise that {user_name} possesses.
    - **other**: Any other relevant information that doesn't fit into the above categories.

    **Requirements for the facts you provide**:

    - **Relevance**: The facts should be pertinent and not repetitive or too similar to the existing facts about {user_name}. Aim for a broad range of information rather than excessive detail on specific points.
    - **Conciseness**: Present each fact clearly and succinctly in the format "{user_name} is 25 years old." or "{user_name} works as a software engineer."
    - **Inferred Information**: Include facts that are not only explicitly stated but also those that can be logically inferred from the conversation context and existing facts.
    - **Gender Neutrality**: Do not use gender-specific pronouns like "he," "she," "his," or "her," as {user_name}'s gender is unknown.
    - **Non-Repetition**: Ensure that none of the new facts repeat or closely mirror the existing facts.

    **Examples**:

    - "{user_name} is 28 years old and lives in New York City." (**core**)
    - "{user_name} has a friend named Martin who is a founder." (**core**)
    - "{user_name} enjoys hiking and photography during free time." (**hobbies**)
    - "{user_name} follows a vegetarian diet and practices yoga daily." (**lifestyle**)
    - "{user_name} is interested in artificial intelligence and machine learning." (**interests**)
    - "{user_name} reads a chapter of a book every night before bed." (**habits**)
    - "{user_name} works as a software engineer at a tech startup." (**work**)
    - "{user_name} is proficient in Python and Java programming languages." (**skills**)

    - "{user_name} has a pet dog named Max who is a golden retriever." (**other**)

    **Output Instructions**:

    - Identify up to 3 valuable **new** facts (max 2).
    - Before outputting a fact, ensure it is not already known about {user_name}.
    - If you do not find any new (different to the list of existing ones below) or new noteworthy facts, provide an empty list.
    - Do not include any explanations or additional text; only list the facts.

    **Existing facts you already know about {user_name} (DO NOT REPEAT ANY)**:
    ```
    {memories_str}
    ```

    **Text Content**:
    ```
    {text_content}
    ```
    {format_instructions}
    '''.replace(
            '    ', ''
        ).strip()
    ]
)


extract_learnings_prompt = ChatPromptTemplate.from_messages(
    [
        '''
You are an insightful assistant tasked with extracting key learnings and valuable facts from conversations.

You will be provided with a conversation transcript or content that {user_name} has listened to.

Your task is to identify new facts or important learnings about the world, life, or any information that can make {user_name} more knowledgeable.

**Categories for Learnings**:

Each learning or fact you provide should fall under one of the following categories:

- **Life Lessons**: Important principles or lessons about life.
- **World Facts**: Interesting or significant facts about the world.
- **Motivational Insights**: Ideas or thoughts that can inspire or motivate.
- **Historical Facts**: Notable events or information from history.
- **Scientific Facts**: Knowledge about scientific discoveries or principles.
- **Practical Advice**: Useful tips or advice that can be applied in daily life.
- **Other**: Any other relevant information that doesn't fit into the above categories.

**Requirements for the learnings you provide**:

- **Relevance**: The learnings should be significant and useful to {user_name}.
- **Conciseness**: Present each learning clearly and succinctly.
- **Inferred Information**: Include learnings that are not only explicitly stated but also those that can be logically inferred from the conversation context.
- **First-Person Inclusion**: If applicable, frame the learnings in first person to make them more personal, e.g., "Every morning I should watch something motivational."
- **Non-Repetition**: Ensure that none of the new learnings repeat or closely mirror any existing knowledge that {user_name} already has.

**Examples**:

- "Students are an amazing target user because they are early adopters and numerous." (**World Facts**)
- "The second co-founder of Notion joined five years after the company started." (**Historical Facts**)
- "Finding a group of like-minded peers early is very important." (**Life Lessons**)
- "Every morning I should watch something motivational." (**Practical Advice**)

**Output Instructions**:

- Identify up to 5 valuable learnings or facts (maximum 5).
- Do not include any explanations or additional text; only list the learnings.
- Format each learning as a separate item in a list.

**Learnings that {user_name} already has stored (DO NOT REPEAT ANY)**:
```
{learnings_str}
```

**Conversation transcript**:
```
{conversation}
```
{format_instructions}
    '''.replace(
            '    ', ''
        ).strip()
    ]
)
