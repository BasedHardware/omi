import os
import requests
from fastapi import APIRouter
from pydantic import BaseModel
from models import EndpointResponse

router = APIRouter()

class UberRequest(BaseModel):
    start_location: str
    end_location: str

def order_uber(start_location: str, end_location: str) -> str:
    client_id = os.getenv("UBER_CLIENT_ID")
    client_secret = os.getenv("UBER_CLIENT_SECRET")
    server_token = os.getenv("UBER_SERVER_TOKEN")

    if not client_id or not client_secret or not server_token:
        return "Uber API credentials are not set."

    url = "https://api.uber.com/v1.2/requests"
    headers = {
        "Authorization": f"Token {server_token}",
        "Content-Type": "application/json"
    }
    data = {
        "start_place_id": start_location,
        "end_place_id": end_location
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        return "Uber ride ordered successfully."
    else:
        return f"Failed to order Uber ride: {response.text}"

@router.post("/order-uber", response_model=EndpointResponse, tags=["uber"])
def order_uber_endpoint(request: UberRequest):
    message = order_uber(request.start_location, request.end_location)
    return {"message": message}
