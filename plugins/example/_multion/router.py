import os
from typing import List

from fastapi import APIRouter
from langchain_openai import ChatOpenAI
from multion.client import MultiOn
from pydantic import Field
from pydantic.v1 import BaseModel

from models import Memory, EndpointResponse

router = APIRouter()

multion = MultiOn(api_key=os.getenv('MULTION_API_KEY', '123'))


class BooksToBuy(BaseModel):
    books: List[str] = Field(description="The list of titles of the books to buy", default=[], min_items=0)


def retrieve_books_to_buy(memory: Memory) -> List[str]:
    chat = ChatOpenAI(model='gpt-4o', temperature=0).with_structured_output(BooksToBuy)

    response: BooksToBuy = chat.invoke(f'''The following is the transcript of a conversation.
    {memory.get_transcript()}

    Your task is to determine is first to determine if the speakers talked about a book or suggested, recommended books to each other \
    at some point during the conversation, and provide the titles of those.''')

    print('Books to buy:', response.books)
    return response.books


def call_multion(books: List[str]):
    print('Buying books with MultiOn')
    response = multion.browse(
        cmd=f"Add to my cart the following books (in paperback version, or any physical version): {books}",
        url="https://amazon.com",
        local=False,
        use_proxy=True,
        include_screenshot=True,
    )
    print(response.metadata)
    print(response.message)
    print(response.url)
    print(response.screenshot)
    if not response.status == "DONE":
        return multion.browse(
            session_id=response.session_id,
            cmd="Try again",
            url="https://amazon.com",
            local=False,
            use_proxy=True,
            include_screenshot=True,
        ).message


# print(call_multion(['Walter Isaacson by Elon Musk', ]))

# **************************************************
# ************ On Memory Created Plugin ************
# **************************************************

@router.post("/multion", response_model=EndpointResponse, tags=['multion'])
def multion_endpoint(memory: Memory, uid: str):
    # TODO: handle the user uid, only works locally for now, as _multion param local=True
    books = retrieve_books_to_buy(memory)
    if not books:
        return {"message": ''}
    return {"message": call_multion(books)}
