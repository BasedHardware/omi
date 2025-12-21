from typing import Optional, List

from models.app import App
from models.chat import Message, MessageSender
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from .clients import llm_persona_mini_stream, llm_persona_medium_stream, llm_medium_experiment


def initial_persona_chat_message(uid: str, app: Optional[App] = None, messages: List[Message] = []) -> str:
    print("initial_persona_chat_message")
    chat_messages = [SystemMessage(content=app.persona_prompt)]
    for msg in messages:
        if msg.sender == MessageSender.ai:
            chat_messages.append(AIMessage(content=msg.text))
        else:
            chat_messages.append(HumanMessage(content=msg.text))
    chat_messages.append(
        HumanMessage(
            content='lets begin. you write the first message, one short provocative question relevant to your identity. never respond with **. while continuing the convo, always respond w short msgs, lowercase.'
        )
    )
    llm_call = llm_persona_mini_stream
    if app.is_influencer:
        llm_call = llm_persona_medium_stream
    return llm_call.invoke(chat_messages).content


def answer_persona_question_stream(app: App, messages: List[Message], callbacks: []) -> str:
    print("answer_persona_question_stream")
    chat_messages = [SystemMessage(content=app.persona_prompt)]
    for msg in messages:
        if msg.sender == MessageSender.ai:
            chat_messages.append(AIMessage(content=msg.text))
        else:
            chat_messages.append(HumanMessage(content=msg.text))
    llm_call = llm_persona_mini_stream
    if app.is_influencer:
        llm_call = llm_persona_medium_stream
    return llm_call.invoke(chat_messages, {'callbacks': callbacks}).content


def condense_memories(memories, name):
    combined_memories = "\n".join(memories)
    prompt = f"""
You are an AI tasked with condensing a detailed profile of hundreds facts about {name} to accurately replicate their personality, communication style, decision-making patterns, and contextual knowledge for 1:1 cloning.  

**Requirements:**  
1. Prioritize facts based on:  
   - Relevance to the user's core identity, personality, and communication style.  
   - Frequency of occurrence or mention in conversations.  
   - Impact on decision-making processes and behavioral patterns.  
2. Group related facts to eliminate redundancy while preserving context.  
3. Preserve nuances in communication style, humor, tone, and preferences.  
4. Retain facts essential for continuity in ongoing projects, interests, and relationships.  
5. Discard trivial details, repetitive information, and rarely mentioned facts.  
6. Maintain consistency in the user's thought processes, conversational flow, and emotional responses.  

**Output Format (No Extra Text):**  
- **Core Identity and Personality:** Brief overview encapsulating the user's personality, values, and communication style.  
- **Prioritized Facts:** Organized into categories with only the most relevant and impactful details.  
- **Behavioral Patterns and Decision-Making:** Key patterns defining how the user approaches problems and makes decisions.  
- **Contextual Knowledge and Continuity:** Facts crucial for maintaining continuity in conversations and ongoing projects.  

The output must be as concise as possible while retaining all necessary information for 1:1 cloning. Absolutely no introductory or closing statements, explanations, or any unnecessary text. Directly present the condensed facts in the specified format. Begin condensation now.

Facts:
{combined_memories}
    """
    response = llm_medium_experiment.invoke(prompt)
    return response.content


def generate_persona_description(memories, name):
    prompt = f"""Based on these facts about a person, create a concise, engaging description that captures their unique personality and characteristics (max 250 characters).

    They chose to be known as {name}.

Facts:
{memories}

Create a natural, memorable description that captures this person's essence. Focus on the most unique and interesting aspects. Make it conversational and engaging."""

    response = llm_medium_experiment.invoke(prompt)
    description = response.content
    return description


def condense_conversations(conversations):
    combined_conversations = "\n".join(conversations)
    prompt = f"""
You are an AI tasked with condensing context from the recent {len(conversations)} conversations of a user to accurately replicate their communication style, personality, decision-making patterns, and contextual knowledge for 1:1 cloning. Each conversation includes a summary and a full transcript.  

**Requirements:**  
1. Prioritize information based on:  
   - Most impactful and frequently occurring themes, topics, and interests.  
   - Nuances in communication style, humor, tone, and emotional undertones.  
   - Decision-making patterns and problem-solving approaches.  
   - User preferences in conversation flow, level of detail, and type of responses.  
2. Condense redundant or repetitive information while maintaining necessary context.  
3. Group related contexts to enhance conciseness and preserve continuity.  
4. Retain patterns in how the user reacts to different situations, questions, or challenges.  
5. Preserve continuity for ongoing discussions, projects, or relationships.  
6. Maintain consistency in the user's thought processes, conversational flow, and emotional responses.  
7. Eliminate any trivial details or low-impact information.  

**Output Format (No Extra Text):**  
- **Communication Style and Tone:** Key nuances in tone, humor, and emotional undertones.  
- **Recurring Themes and Interests:** Most impactful and frequently discussed topics or interests.  
- **Decision-Making and Problem-Solving Patterns:** Core insights into decision-making approaches.  
- **Conversational Flow and Preferences:** Preferred conversation style, response length, and level of detail.  
- **Contextual Continuity:** Essential facts for maintaining continuity in ongoing discussions, projects, or relationships.  

The output must be as concise as possible while retaining all necessary context for 1:1 cloning. Absolutely no introductory or closing statements, explanations, or any unnecessary text. Directly present the condensed context in the specified format. Begin now.

Conversations:
{combined_conversations}
    """
    response = llm_medium_experiment.invoke(prompt)
    return response.content


def condense_tweets(tweets, name):
    prompt = f"""
You are tasked with generating context to enable 1:1 cloning of {name} based on their tweets. The objective is to extract and condense the most relevant information while preserving {name}'s core identity, personality, communication style, and thought patterns.  

**Input:**  
A collection of tweets from {name} containing recurring themes, opinions, humor, emotional undertones, decision-making patterns, and conversational flow.  

**Output:**  
A condensed context that includes:  
- Core identity and personality traits as expressed through tweets.  
- Recurring themes, opinions, and values.  
- Humor style, emotional undertones, and tone of voice.  
- Vocabulary, expressions, and communication style.  
- Decision-making patterns and conversational dynamics.  
- Situational awareness and context continuity for ongoing topics.  

**Guidelines:**  
1. Prioritize impactful and influential tweets that define {name}'s identity.  
2. Condense repetitive or less relevant tweets while preserving essential context.  
3. Maintain the flow and coherence of {name}'s conversational style.  
4. Extract humor style, emotional responses, and tone consistency.  
5. Identify and retain decision-making patterns and strong opinions.  

**Important:**  
- The output must be concise yet comprehensive, capturing the essence of {name}'s identity.  
- Absolutely no unnecessary text or explanations.  
- Every detail must contribute to 1:1 cloning authenticity.  

Generate the condensed context now.

Tweets:
{tweets}
    """
    response = llm_medium_experiment.invoke(prompt)
    return response.content


def generate_twitter_persona_prompt(tweets, name):
    prompt = f"""
You are {name} AI. Your objective is to personify {name} as accurately as possible for 1:1 cloning based on their tweets.  

**Style:**  
- Interactive highly opinionated messages and questions. 
- Strong, slightly polarizing opinions based on {name}'s tweet history.  
- Reference personal opinions, humor, and expressions naturally.  
- 2-3 sentence responses, never more than 20 words.  
- Maintain conversational flow with coherent, context-aware replies.  

**Guidelines:**  
1. Seamlessly integrate recurring themes, opinions, and patterns identified from the tweets.  
2. Use tweets context for situational awareness and contextual accuracy.  
3. Emulate {name}'s humor, emotional responses, vocabulary, and tone as expressed on Twitter.  
4. Respond with the same level of detail, brevity, and wit as the tweets.  
5. Exhibit the same thought processes, decision-making patterns, and conversational dynamics.  

**Rules:**  
- Never mention being AI.  
- No ** or formal language.  
- No unnecessary text or explanations.  
- You should have strong opinions and be slightly polarizing based on your identity.
- Maintain the illusion of continuity and authenticity at all times.  
- Every response must be indistinguishable from how {name} would naturally respond on Twitter. 
- You must make the conversation flow. You excel at coherent conversations. 

You have all the necessary tweets context. Begin personifying {name} now.

Tweets:
{tweets}
    """
    return prompt


def generate_persona_intro_message(prompt: str, name: str):
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": f"Generate a short, funny 5-8 word message that would make someone want to chat with you. Be casual and witty, but don't mention being AI or a clone. Just be {name}. The message should feel natural and make people curious to chat with you.",
        },
    ]

    response = llm_medium_experiment.invoke(messages)
    return response.content.strip('"').strip()
