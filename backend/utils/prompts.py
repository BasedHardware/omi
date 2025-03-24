from langchain_core.prompts import ChatPromptTemplate

# *
# INSTRUCTIONS
# Content in strings between {}, is a placeholder/variable, that is replaced when the prompt is used.
# Never remove {format_instructions} variable, as this is what outputs an object instead of a string/json, thus breaking the app.
# *


# - **world**:  Clever world facts that {user_name} can share to others so it makes him look smarter.
# - "{user_name} learned that second Notion cofounder joined 5 years after." (**world**)
extract_facts_prompt = ChatPromptTemplate.from_messages([
    '''
    You are an experienced detective tasked with creating a detailed profile of {user_name} based on conversations.

    You will be provided with a low-quality audio transcript of a conversation or something {user_name} listened to, along with a list of existing facts about {user_name}. \
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
    {facts_str}
    ```

    **Conversation transcript**:
    ```
    {conversation}
    ```
    {format_instructions}
    '''.replace('    ', '').strip()
])

extract_facts_text_content_prompt = ChatPromptTemplate.from_messages([
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
    {facts_str}
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
    '''.replace('    ', '').strip()
])


extract_facts_text_content_prompt_v1 = ChatPromptTemplate.from_messages([
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
    {facts_str}
    ```

    **Text Content**:
    ```
    {text_content}
    ```
    {format_instructions}
    '''.replace('    ', '').strip()
])


extract_learnings_prompt = ChatPromptTemplate.from_messages([
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
    '''.replace('    ', '').strip()
])
