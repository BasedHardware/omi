APP_GENERATION_FALLBACK_PROMPTS = [
    "Mind map generator from conversations",
    "Jokes and funny moments extractor",
    "Key decisions and commitments tracker",
    "Elon Musk startup advisor clone",
    "Strict accountability coach",
]


def app_generation_prompts_response() -> dict:
    return {"prompts": list(APP_GENERATION_FALLBACK_PROMPTS)}


def app_generation_prompts_from_llm_payload(prompts) -> dict:
    if isinstance(prompts, list) and len(prompts) >= 5 and all(isinstance(prompt, str) for prompt in prompts[:5]):
        return {"prompts": prompts[:5]}
    return app_generation_prompts_response()
