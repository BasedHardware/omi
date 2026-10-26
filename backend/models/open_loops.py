"""Open-loop Review card wire contract shared with the mobile client.

Only what the card writer renders for the owner crosses the wire: the
self-contained question and context line. Loop ids, ranking values, task links
and other store internals stay server-side.
"""

from typing import Literal

from pydantic import BaseModel, Field

OpenLoopAction = Literal['done', 'remind', 'drop']
OpenLoopAnswerState = Literal['done', 'remind', 'dropped']

# The card state each answer leaves, mirroring the service's CARD_STATE_BY_ACTION.
OPEN_LOOP_ANSWER_STATE: dict[OpenLoopAction, OpenLoopAnswerState] = {
    'done': 'done',
    'remind': 'remind',
    'drop': 'dropped',
}


class OpenLoopCard(BaseModel):
    card_id: str
    date: str
    question: str
    context_line: str


class OpenLoopCardsResponse(BaseModel):
    cards: list[OpenLoopCard] = Field(default_factory=list)


class OpenLoopAnswerRequest(BaseModel):
    action: OpenLoopAction


class OpenLoopAnswerResponse(BaseModel):
    card_id: str
    date: str
    state: OpenLoopAnswerState
