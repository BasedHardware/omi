from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class TrendEnum(str, Enum):
    ceo = "ceo"
    company = "company"
    software_product = "software_product"
    hardware_product = "hardware_product"
    ai_product = "ai_product"


class TrendType(str, Enum):
    best = "best"
    worst = "worst"


class Trend(BaseModel):
    category: TrendEnum = Field(description="The category identified")
    type: TrendType = Field(description="The type of trend identified")
    topics: List[str] = Field(description="The specific topic corresponding the category")


ceo_options = [
    "Elon Musk",
    "Sundar Pichai",
    "Satya Nadella",
    "Jensen Huang",
    "Andy Jassy",
    "Ryan Breslow",
    "Henrique Dubugras",
    "Alexandr Wang",
    "Tim Cook",
    "Marc Benioff",
    "Dylan Field",
    "Parag Agrawal",
    "Brian Chesky",
    "Patrick Collison",
    "Andrew Wilson",
    "Lisa Su",
    "Austin Russell",
    "Sam Altman",
    "Darius Adamczyk",
    "Shantanu Narayen",
    "Bob Chapek",
    "Mark Zuckerberg",
    "David Zaslav",
    "Mary Barra",
    "Howard Schultz",
    "Raj Subramaniam",
    "Arvind Krishna",
    "Adam Neumann",
    "Vlad Tenev",
    "Dara Khosrowshahi",
    "Fran Horowitz",
    "Yuanqing Yang",
    "Frank Slootman",
    "William McDermott",
    "Anthony Wood",
    "Roland Busch",
    "Christian Klein",
    "Kazuhiro Tsuga",
    "Stéphane Bancel"
]

company_options = [
    "Microsoft",
    "Nvidia",
    "Amazon",
    "Apple",
    "Tesla",
    "Salesforce",
    "Shopify",
    "Google/Alphabet",
    "SpaceX",
    "OpenAI",
    "Brex",
    "Stripe",
    "Adobe",
    "Zoom",
    "Figma",
    "Databricks",
    "GitHub",
    "Luminar",
    "Airbnb",
    "Square",
    "Meta",
    "Warner Bros. Discovery",
    "Disney",
    "X (formerly Twitter)",
    "BP",
    "Robinhood",
    "Peloton",
    "Boeing",
    "WeWork",
    "FedEx",
    "AT&T",
    "IBM",
    "Frontier Airlines",
    "Uber",
    "Juul",
    "TikTok",
    "Snapchat",
    "Nestlé",
    "Facebook",
    "GameStop"
]

software_product_options = [
    "Microsoft Copilot",
    "OpenAI GPT-4",
    "Slack",
    "Google Workspace",
    "Zoom",
    "Salesforce CRM",
    "Adobe Photoshop",
    "Figma",
    "Datadog",
    "ServiceNow",
    "HubSpot",
    "Notion",
    "Tableau",
    "Monday.com",
    "GitHub Copilot",
    "Asana",
    "Trello",
    "Snowflake",
    "Atlassian Jira",
    "ZoomInfo",
    "Meta Horizon Worlds",
    "Robinhood",
    "Oracle",
    "Evernote",
    "Google Stadia",
    "Facebook Workplace",
    "SAP S/4HANA",
    "IBM Watson",
    "Quibi",
    "Kaspersky",
    "Palantir",
    "Clubhouse",
    "Slack Threads",
    "TikTok’s Creator Tools",
    "Samsung Bixby",
    "Salesforce Marketing Cloud",
    "Microsoft Teams",
    "Intel AI Suite",
    "Uber Driver App"
]

hardware_product_options = [
    "Tesla Cybertruck",
    "iPhone 16",
    "MacBook Pro",
    "Nvidia RTX 5090",
    "SpaceX Starship",
    "Amazon Echo",
    "Sony PlayStation 6",
    "Microsoft Surface Pro 10",
    "Dyson V16",
    "Luminar LiDAR",
    "DJI Mavic 3",
    "Apple Vision Pro",
    "Google Pixel 9",
    "Framework Laptop",
    "Oculus Quest 4",
    "Logitech G Pro X",
    "Samsung Galaxy Fold 4",
    "Fitbit Charge 6",
    "Apple Watch 9",
    "Lumix S5 II"
]

ai_product_options = [
    "OpenAI GPT-5",
    "Google DeepMind",
    "Nvidia Omniverse",
    "Microsoft Copilot",
    "Tesla FSD",
    "Amazon Alexa",
    "Salesforce Einstein",
    "Palantir Foundry",
    "Scale AI",
    "Grammarly AI",
    "MidJourney",
    "Hugging Face",
    "Runway Gen-2",
    "Anthropic Claude 2",
    "Cohere",
    "Databricks AI",
    "Hugging Face Transformers",
    "Notion AI",
    "Synthesia",
    "Jasper AI",
    "Meta AI",
    "IBM Watson",
    "Clearview AI",
    "Facebook AI",
    "Google Duplex",
    "Samsung Bixby",
    "Twitter AI moderation",
    "Microsoft Tay",
    "Replika",
    "Clear AI",
    "TikTok AI",
    "Robinhood AI Trading",
    "Meta Horizon AI",
    "Ring AI",
    "Uber AI",
    "Watson Health",
    "ChatGPT clones",
    "Tinder AI",
    "Zoom AI transcription",
    "Salesforce AI"
]

valid_items = set(
    ceo_options + company_options + software_product_options + hardware_product_options + ai_product_options)
