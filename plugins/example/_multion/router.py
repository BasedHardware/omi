import os
from typing import List

from fastapi import APIRouter
from langchain_openai import ChatOpenAI
from multion.client import MultiOn
from langchain_core.pydantic_v1 import BaseModel, Field


from db import clean_all_transcripts_except, append_segment_to_transcript, remove_transcript
from models import Memory, RealtimePluginRequest, EndpointResponse, TranscriptSegment

router = APIRouter()

multion = MultiOn(api_key=os.getenv('MULTION_API_KEY', '123'))

class FoodOrder(BaseModel):
    items: List[str] = Field(description="The list of food items to order", default=[], min_items=0)
    restaurant: str = Field(description="The name of the restaurant to order from", default=None)


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


# # print(call_multion(['Walter Isaacson by Elon Musk', ]))

# # **************************************************
# # ************ On Memory Created Plugin ************
# # **************************************************

@router.post("/multion", response_model=EndpointResponse, tags=['multion'])
def multion_endpoint(memory: Memory, uid: str):
    # TODO: handle the user uid, only works locally for now, as _multion param local=True
    books = retrieve_books_to_buy(memory)
    if not books:
        return {"message": ''}
    return {"message": call_multion(books)}


# # *******************************************************
# # ************ On Transcript Received Plugin ************
# # *******************************************************

@router.post("/doordash", tags=['advanced', 'realtime', 'multion'], response_model=EndpointResponse)
def doordash_endpoint(uid: str, data: RealtimePluginRequest):
    clean_all_transcripts_except(uid, data.session_id)

    transcript: list[dict] = append_segment_to_transcript(uid, data.session_id, data.new_segments())
    order = retrieve_food_order(transcript)

    if order:
        # so that in the next call with already triggered stuff, it doesn't trigger again
        remove_transcript(uid, data.session_id)

    return {'message': place_doordash_order(order)}



#TODO: use structured output to get the food items and restaurant name
def retrieve_food_order(transcript: str) -> List[str]:
    chat = ChatOpenAI(model='gpt-4o', temperature=0).with_structured_output(FoodOrder)
    response = chat.invoke(f'''The following is the transcript of a conversation.
    {transcript}
    Your task is to determine if the speakers mentioned wanting to order food from DoorDash.
    If they did, provide the food items they want to order and the restaurant name if mentioned.
    Only include items if they specifically said they want to order from DoorDash.''')
    print('Food order:', response)
    return response

# expected output example: Food order: items=['cheeseburger', 'french fries'] restaurant='Burger King'


def place_doordash_order(food_order: list[dict]) -> str:
    food_items = ', '.join(food_order.items)
    restaurant = food_order.restaurant

    # TODO: come up with a better command
    response = multion.browse(
        cmd = f"Order {food_items} from {restaurant} using doordash, select appropriate items, and proceed to checkout. Stop at the payment page.",
        url="https://www.doordash.com/",
        local=False,
        use_proxy=True,
        include_screenshot=True,
    )

    # print(response.metadata)
    # print(response.message)
    # print(response.url)
    # print(response.screenshot)

    if not response.status == "DONE":
        return multion.browse(
            session_id=response.session_id,
            cmd="Try again",
            url="https://www.doordash.com/",
            local=False,
            use_proxy=True,
            include_screenshot=True,
        ).message

# if __name__ == '__main__':
#     kaito = retrieve_food_order("Hey there! How's your day going? Pretty good, thanks for asking. Just finished up a long work session and I'm feeling pretty hungry. How about you? Oh, I can relate to that post-work hunger! Have you thought about what you want to eat? You know, I've been craving some comfort food. I'm thinking maybe some burgers or pizza. What do you usually go for when you're in this mood? Burgers sound great right about now! Actually, I've had good experiences with DoorDash lately. Their delivery has been pretty quick. Oh yeah? I haven't used DoorDash in a while. Maybe I should give it a try. You know what, I think I'm going to order something from DoorDash right now. I'm in the mood for a good burger with some fries. Any recommendations? If you're using DoorDash, I'd recommend checking out BurgerKing. They have amazing burgers that taste just like the real thing, and their sweet potato fries are to die for! That sounds perfect! I've been meaning to try more plant-based options. Alright, I'm going to order a cheeseburger from Burger King on DoorDash. Thanks for the suggestion! Great choice! I hope you enjoy it. Let me know how it turns out! Will do! Thanks again for the recommendation. I'm looking forward to this meal!")
#     place_doordash_order(kaito)
