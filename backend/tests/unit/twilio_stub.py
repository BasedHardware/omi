import importlib.util
import sys
import types
from html import escape


def install_twilio_stub():
    if 'twilio' in sys.modules or importlib.util.find_spec('twilio') is not None:
        return

    twilio_mod = types.ModuleType('twilio')
    rest_mod = types.ModuleType('twilio.rest')
    jwt_mod = types.ModuleType('twilio.jwt')
    access_token_mod = types.ModuleType('twilio.jwt.access_token')
    grants_mod = types.ModuleType('twilio.jwt.access_token.grants')
    request_validator_mod = types.ModuleType('twilio.request_validator')
    base_mod = types.ModuleType('twilio.base')
    exceptions_mod = types.ModuleType('twilio.base.exceptions')
    twiml_mod = types.ModuleType('twilio.twiml')
    voice_response_mod = types.ModuleType('twilio.twiml.voice_response')

    twilio_mod.__path__ = []
    jwt_mod.__path__ = []
    base_mod.__path__ = []
    twiml_mod.__path__ = []

    class Client:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class AccessToken:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.grants = []

        def add_grant(self, grant):
            self.grants.append(grant)

        def to_jwt(self):
            return 'test.jwt.token'

    class VoiceGrant:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class RequestValidator:
        def __init__(self, token):
            self.token = token

        def validate(self, url, params, signature):
            return False

    class TwilioRestException(Exception):
        def __init__(self, status=None, uri=None, msg=None, code=None, method=None, details=None):
            super().__init__(msg)
            self.status = status
            self.uri = uri
            self.msg = msg
            self.code = code
            self.method = method
            self.details = details

    def _xml_attrs(attrs):
        rendered = [f'{name}="{escape(str(value), quote=True)}"' for name, value in attrs.items() if value is not None]
        return f" {' '.join(rendered)}" if rendered else ''

    class VoiceResponse:
        def __init__(self):
            self.verbs = []

        def say(self, text):
            self.verbs.append(f'<Say>{escape(str(text))}</Say>')

        def append(self, verb):
            self.verbs.append(str(verb))

        def __str__(self):
            return f'<?xml version="1.0" encoding="utf-8"?><Response>{"".join(self.verbs)}</Response>'

    class Number:
        def __init__(self, phone_number):
            self.phone_number = phone_number

        def __str__(self):
            return f'<Number>{escape(str(self.phone_number))}</Number>'

    class Dial:
        def __init__(self, caller_id=None, time_limit=None, **kwargs):
            self.caller_id = caller_id
            self.time_limit = time_limit
            self.kwargs = kwargs
            self.number_verbs = []

        def number(self, phone_number):
            number_verb = Number(phone_number)
            self.number_verbs.append(number_verb)
            return number_verb

        def __str__(self):
            attrs = _xml_attrs({'callerId': self.caller_id, 'timeLimit': self.time_limit})
            numbers = ''.join(str(number_verb) for number_verb in self.number_verbs)
            return f'<Dial{attrs}>{numbers}</Dial>'

    rest_mod.Client = Client
    access_token_mod.AccessToken = AccessToken
    grants_mod.VoiceGrant = VoiceGrant
    request_validator_mod.RequestValidator = RequestValidator
    exceptions_mod.TwilioRestException = TwilioRestException
    voice_response_mod.VoiceResponse = VoiceResponse
    voice_response_mod.Dial = Dial
    voice_response_mod.Number = Number

    twilio_mod.rest = rest_mod
    twilio_mod.jwt = jwt_mod
    jwt_mod.access_token = access_token_mod
    access_token_mod.grants = grants_mod
    twilio_mod.request_validator = request_validator_mod
    twilio_mod.base = base_mod
    base_mod.exceptions = exceptions_mod
    twilio_mod.twiml = twiml_mod
    twiml_mod.voice_response = voice_response_mod

    sys.modules.setdefault('twilio', twilio_mod)
    sys.modules.setdefault('twilio.rest', rest_mod)
    sys.modules.setdefault('twilio.jwt', jwt_mod)
    sys.modules.setdefault('twilio.jwt.access_token', access_token_mod)
    sys.modules.setdefault('twilio.jwt.access_token.grants', grants_mod)
    sys.modules.setdefault('twilio.request_validator', request_validator_mod)
    sys.modules.setdefault('twilio.base', base_mod)
    sys.modules.setdefault('twilio.base.exceptions', exceptions_mod)
    sys.modules.setdefault('twilio.twiml', twiml_mod)
    sys.modules.setdefault('twilio.twiml.voice_response', voice_response_mod)
