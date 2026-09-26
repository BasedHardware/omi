```python
from ..models import AutoVoiceModel
from ..utils.log_sanitizer import sanitize
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class AutoVoiceRouter:
    def __init__(self):
        self.model = AutoVoiceModel()

    async def router(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Auto model selection and scoring"""
        if not request or "body" not in request:
            return {"code": 400, "msg": "Bad request format"}
        
        body = request.get("body", {})
        if not body or "uid" not in body:
            return {"code": 401, "msg": "Unauthorized"}
        
        uid = body.get("uid", "")
        if len(uid.strip()) == 0:
            return {"code": 401, "msg": "Unauthorized"}
        
        try:
            metrics = self.model.score(uid)
            
            quality = float(metrics.get("quality", 0))
            speed = float(metrics.get("speed", 0))
            
            score = 0.5 * (quality + speed)
            if score < 0:
                score = 0
            elif score > 1:
                score = 1
            
            return {"score": score}
            
        except Exception as e:
            logger.error(sanitize(str(e)))
            return {
                "code": 500,
                "msg": "Internal Service Error",
                "detail": {"reason": "model scoring fetch failed; default to Gemini"}
            }
```