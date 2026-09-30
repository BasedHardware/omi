"""
Mobile feedback router.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.database.feedback import record_feedback_event

router = APIRouter(prefix="/api/v1/mobile/feedback", tags=["mobile_feedback"])


@router.post("/submit")
async def submit_mobile_feedback(request: Request) -> JSONResponse:
    """
    Submit mobile feedback.
    
    Expects JSON body with:
    - uid: User identifier
    - target_id: Target identifier
    - feedback_type: Type of feedback
    - metadata: Optional metadata
    - feedback_id: Optional feedback ID
    """
    try:
        body = await request.json()
        feedback_id = record_feedback_event(
            uid=body["uid"],
            target_id=body["target_id"],
            feedback_type=body["feedback_type"],
            metadata=body.get("metadata"),
            feedback_id=body.get("feedback_id"),
        )
        return JSONResponse(content={"status": "ok", "feedback_id": feedback_id})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing required field: {exc.args[0]}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error")
