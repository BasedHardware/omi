from typing import Union
import re
from ._types import Options
from .keys import Keys
from .transcription import Transcription
from .projects import Projects
from .usage import Usage
from .billing import Billing
from .members import Members
from .scopes import Scopes
from .invitations import Invitations
from .extra import Extra
from .errors import DeepgramSetupError, DeepgramApiError


def api_key_is_valid(api_key: str) -> bool:
    pattern = r"^[a-f0-9]{40}$"
    return re.match(pattern, api_key) is not None


class Deepgram:
    def __init__(self, options: Union[str, Options]) -> None:
        if not isinstance(options, (str, dict)):
            raise DeepgramSetupError("`options` must be a dictionary or an API key string")

        # Convert to dictionary if the api key was passed as a string
        if isinstance(options, str):
            options: Options = {"api_key": options}

        if "api_key" not in options:
            raise DeepgramSetupError("API key is required")
        if not api_key_is_valid(options["api_key"]):
            raise DeepgramSetupError("Invalid API key")

        if "api_url" in options and options.get("api_url", None) is None:
            raise DeepgramSetupError("API URL must be valid or omitted")

        self.options = options

    @property
    def keys(self) -> Keys:
        return Keys(self.options)

    @property
    def transcription(self) -> Transcription:
        return Transcription(self.options)

    @property
    def projects(self) -> Projects:
        return Projects(self.options)

    @property
    def usage(self) -> Usage:
        return Usage(self.options)

    @property
    def billing(self) -> Billing:
        return Billing(self.options)

    @property
    def members(self) -> Members:
        return Members(self.options)

    @property
    def scopes(self) -> Scopes:
        return Scopes(self.options)

    @property
    def invitations(self) -> Invitations:
        return Invitations(self.options)

    @property
    def extra(self) -> Extra:
        return Extra(self.options)


__all__ = [Deepgram, DeepgramSetupError, DeepgramApiError]
