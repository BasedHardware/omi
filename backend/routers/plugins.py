# TODO: delete this file after the PR 2342 is merged and a new app ver is live on prod

from fastapi import APIRouter

router = APIRouter()


@router.get('/v1/plugin-categories', tags=['v1'])
def get_plugin_categories():
    return [
        {'title': 'Conversation Analysis', 'id': 'conversation-analysis'},
        {'title': 'Personality Emulation', 'id': 'personality-emulation'},
        {'title': 'Health and Wellness', 'id': 'health-and-wellness'},
        {'title': 'Education and Learning', 'id': 'education-and-learning'},
        {'title': 'Communication Improvement', 'id': 'communication-improvement'},
        {'title': 'Emotional and Mental Support', 'id': 'emotional-and-mental-support'},
        {'title': 'Productivity and Organization', 'id': 'productivity-and-organization'},
        {'title': 'Entertainment and Fun', 'id': 'entertainment-and-fun'},
        {'title': 'Financial', 'id': 'financial'},
        {'title': 'Travel and Exploration', 'id': 'travel-and-exploration'},
        {'title': 'Safety and Security', 'id': 'safety-and-security'},
        {'title': 'Shopping and Commerce', 'id': 'shopping-and-commerce'},
        {'title': 'Social and Relationships', 'id': 'social-and-relationships'},
        {'title': 'News and Information', 'id': 'news-and-information'},
        {'title': 'Utilities and Tools', 'id': 'utilities-and-tools'},
        {'title': 'Other', 'id': 'other'},
    ]
