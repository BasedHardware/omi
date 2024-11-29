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

    - Identify up to 3 valuable **new** facts (max 3).
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
