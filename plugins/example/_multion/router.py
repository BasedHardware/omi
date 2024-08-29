import os
from typing import List, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from db import store_multion_user_id, get_multion_user_id
from langchain_openai import ChatOpenAI
from multion.client import MultiOn
from pydantic import Field
from pydantic.v1 import BaseModel
import json
import httpx
import asyncio
from fastapi import HTTPException, Query
from pydantic import Field

from models import Memory, EndpointResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")


GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MULTION_API_KEY = os.getenv('MULTION_API_KEY', '123')


class BooksToBuy(BaseModel):
    books: List[str] = Field(description="The list of titles of the books to buy", default=[], min_items=0)

async def retrieve_books_to_buy(memory: Memory) -> List[str]:
    groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
    Analyze the following transcript and identify any book titles mentioned or suggested:

    {memory.transcript}

    Return only a JSON array of book titles, without any additional text. If no books are mentioned or suggested, return an empty array.
    """

    payload = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 150
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(groq_api_url, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()
        
        content = response_data['choices'][0]['message']['content']
        print(f"Raw GROQ API response: {content}")
        
        # Extract the JSON array from the content
        import re
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            book_titles = json.loads(json_match.group())
        else:
            raise ValueError("No JSON array found in the response")
        
        print('Books to buy:', book_titles)
        return book_titles
    except Exception as e:
        print(f"Error in retrieve_books_to_buy: {e}")
        return []

async def call_multion(books: List[str], user_id: str):
    print(f'Buying books with MultiOn for user_id: {user_id}')
    headers = {
        "X_MULTION_API_KEY": MULTION_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "url": "https://amazon.com",
        "cmd": f"Add to my cart the following books (in paperback version, or any physical version): {books}. Only add the books, do not add anything else. and then say success.",
        "user_id": user_id,
        "local": False,
        "use_proxy": True,
        "include_screenshot": True
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            print(f"Sending request to Multion API: {data}")
            response = await client.post(
                "https://api.multion.ai/v1/web/browse",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            result = response.json()
            print(f"MultiOn API response: {result}")
            if result.get('status') != "DONE":
                return await retry_multion(result.get('session_id'))
            return result.get('message')
    except httpx.HTTPStatusError as e:
        print(f"HTTP error occurred: {e.response.status_code} {e.response.text}")
        raise
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r}.")
        raise
    except Exception as e:
        print(f"Unexpected error in call_multion: {str(e)}")
        raise

async def retry_multion(session_id: str):
    headers = {
        "X_MULTION_API_KEY": MULTION_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "session_id": session_id,
        "cmd": "Try again",
        "url": "https://amazon.com",
        "local": False,
        "use_proxy": True,
        "include_screenshot": True
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.multion.ai/v1/web/browse",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            return response.json().get('message')
    except httpx.HTTPStatusError as e:
        print(f"HTTP error occurred: {e.response.status_code} {e.response.text}")
        return f"HTTP error: {e.response.status_code}"
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r}.")
        return f"Request error: {str(e)}"
    except Exception as e:
        print(f"Unexpected error in retry_multion: {str(e)}")
        return f"Unexpected error: {str(e)}"

async def process_transcript_task(task_id: str, full_transcript: str, uid: str):
    try:
        import db
        db.set_task_status(task_id, "PROCESSING")
        
        memory = Memory(transcript=full_transcript)
        books = await retrieve_books_to_buy(memory)
        
        if not books:
            db.set_task_status(task_id, "COMPLETED")
            db.set_task_result(task_id, "No books were suggested or mentioned.")
            return
        
        user_id = db.get_multion_user_id(uid)
        if not user_id:
            db.set_task_status(task_id, "ERROR")
            db.set_task_result(task_id, f"No user_id found for uid: {uid}")
            return
        
        # Decode user_id if it's bytes
        if isinstance(user_id, bytes):
            user_id = user_id.decode('utf-8')
        
        print(f"Calling Multion API for user_id: {user_id}")
        
        # Call Multion API with a timeout
        try:
            result = await asyncio.wait_for(call_multion(books, user_id), timeout=120)
        except asyncio.TimeoutError:
            db.set_task_status(task_id, "TIMEOUT")
            db.set_task_result(task_id, "Multion API request timed out after 120 seconds.")
            return
        except Exception as e:
            db.set_task_status(task_id, "ERROR")
            db.set_task_result(task_id, f"Error calling Multion API: {str(e)}")
            return
        
        if isinstance(result, bytes):
            result = result.decode('utf-8')
        
        db.set_task_status(task_id, "COMPLETED")
        db.set_task_result(task_id, result)
    except Exception as e:
        db.set_task_status(task_id, "ERROR")
        db.set_task_result(task_id, f"Unexpected error: {str(e)}")
    finally:
        print(f"Task {task_id} finished with status: {db.get_task_status(task_id)}")
        print(f"Task result: {db.get_task_result(task_id)}")
        
async def call_multion(books: List[str], user_id: str):
    print('Buying books with MultiOn')
    headers = {
        "X_MULTION_API_KEY": MULTION_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "url": "https://amazon.com",
        "cmd": f"Add to my cart the following books (in paperback version, or any physical version): {books}. Only add the books, do not add anything else. and then say success.",
        "user_id": user_id,
        "local": False,
        "use_proxy": True,
        "include_screenshot": True
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.multion.ai/v1/web/browse",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        result = response.json()
        print(f"MultiOn API response: {result}")
        if result.get('status') != "DONE":
            return await retry_multion(result.get('session_id'))
        return result.get('message')

@router.post("/multion", response_model=EndpointResponse, tags=['multion'])
async def multion_endpoint(memory: Memory, uid: str = Query(...)):
    import db
    user_id = db.get_multion_user_id(uid)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid UID or USERID not found.")
    
    books = await retrieve_books_to_buy(memory)
    if not books:
        return EndpointResponse(message='No books were suggested or mentioned.')
    result = await call_multion(books, user_id)
    
    if isinstance(result, bytes):
        result = result.decode('utf-8')
    
    return EndpointResponse(message=result)\
    
__all__ = ["router", "process_transcript_task"]