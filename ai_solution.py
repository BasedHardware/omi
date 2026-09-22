```python
from typing import List, Optional, Dict
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from ..base import BaseAPI
from ..base.models import OMILocalizedString
import logging
from .ms365_auth import MicrosoftTeamsConnector

logger = logging.getLogger(__name__)

class Ms365App(BaseAPI):
    def _auth_guard(self, tool_name: str) -> None:
        try:
            self.ms_teamsConnector.check_auth()
        except auth.AuthError as e:
            logger.warning(
                "Authentication error: %s",
                str(e),
                exc_info=True,
            )
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                str(OMILocalizedString("Microsoft not connected — please connect in settings.")),
            ) from None

    async def tool_dispatch(
        self,
        tool_name: str,
        tool_input: str,
        parameters: Optional[Dict[str, Optional[str]]] = None,
    ) -> JSONResponse:
        try:
            tool_class = self.tool_classes[tool_name]
            tool = tool_class()
            output = await tool.call_async(
                tool_input,
                parameters=parameters,
            )
            return JSONResponse(
                content=jsonable_encoder(output),
                status_code=status.HTTP_200_OK,
            )
        except TypeError as e:
            logger.warning(
                "Bad arguments for %s: %s",
                tool_name,
                str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=OMILocalizedString(f"Bad arguments for {tool_name}"),
            ) from None
        except Exception as e:
            logger.error(
                "Error in tool %s: %s",
                tool_name,
                str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=OMILocalizedString("An unexpected error occurred"),
            ) from None
```