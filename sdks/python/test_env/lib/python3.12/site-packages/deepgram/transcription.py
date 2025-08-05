from typing import Any, Union, Tuple, List, Dict, Awaitable, cast
import json
import asyncio
import inspect
from enum import Enum
from warnings import warn
import websockets.client
import websockets.exceptions
from ._types import (Options, PrerecordedOptions, LiveOptions, ToggleConfigOptions,
                     TranscriptionSource, PrerecordedTranscriptionResponse,
                     LiveTranscriptionResponse, Metadata, EventHandler)
from ._enums import LiveTranscriptionEvent
from ._utils import _request, _sync_request, _make_query_string, _socket_connect
from .errors import DeepgramApiError


class PrerecordedTranscription:
    """This class provides an interface for doing transcription asynchronously on prerecorded audio files."""

    _root = "/listen"

    def __init__(self, options: Options,
                 transcription_options: PrerecordedOptions, endpoint) -> None:
        """
        This function initializes the options and transcription_options for the PrerecordedTranscription class.

        :param options:Options: Used to Pass in the options for the transcription.
        :param transcription_options:PrerecordedOptions: Used to Specify the transcription options for a prerecorded audio file.
        :return: Nothing.

        """
        self.options = options
        if endpoint is not None:
            self._root = endpoint
        self.transcription_options = transcription_options

    async def __call__(
        self, source: TranscriptionSource, timeout: float = None
    ) -> PrerecordedTranscriptionResponse:
        """
        The __call__ function is a special method that allows the class to be called
        as a function. This is useful for creating instances of the class, where we can
        call `PrerecordedTranscription()` and pass in arguments to set up an instance of
        the class. For example:
        
            prerecorded_transcription = PrerecordedTranscription(...)
        
        :param source:TranscriptionSource: Used to Pass in the audio file.
        :param timeout:float: (optional) The request timeout (if not set, defaults to `aiohttp`'s default timeout)
        :return: A `PrerecordedTranscriptionResponse` object, which contains the transcription results.
        
        """

        if 'buffer' in source and 'mimetype' not in source:
            raise DeepgramApiError(
                'Mimetype must be provided if the source is bytes',
                http_library_error=None,
            )
        payload = cast(
            Union[bytes, Dict],
            source.get('buffer', {'url': source.get('url')})
        )
        content_type = cast(str, source.get('mimetype', 'application/json'))
        return await _request(
            f'{self._root}{_make_query_string(self.transcription_options)}',
            self.options, method='POST', payload=payload,
            headers={'Content-Type': content_type},
            timeout=timeout
        )


class SyncPrerecordedTranscription:
    """This class provides an interface for doing transcription synchronously on prerecorded audio files."""

    _root = "/listen"

    def __init__(self, options: Options,
                 transcription_options: PrerecordedOptions, endpoint) -> None:
        """
        This function initializes the options and transcription_options for the PrerecordedTranscription class.

        :param options:Options: Used to Pass in the options for the transcription.
        :param transcription_options:PrerecordedOptions: Used to Specify the transcription options for a prerecorded audio file.
        :return: Nothing.

        """

        self.options = options
        if endpoint is not None:
            self._root = endpoint
        self.transcription_options = transcription_options

    def __call__(
        self, source: TranscriptionSource, timeout: float = None
    ) -> PrerecordedTranscriptionResponse:

        """
        The __call__ function is a special method that allows the class to be called
        as a function. This is useful for creating instances of the class, where we can
        call `SyncPrerecordedTranscription()` and pass in arguments to set up an instance of
        the class. For example:
        
            sync_prerecorded_transcription = SyncPrerecordedTranscription(...)
        
        :param source:TranscriptionSource: Used to Pass in the audio file.
        :param timeout:float: (optional) The request timeout, excluding the upload time of the audio file.
        :return: A `prerecordedtranscriptionresponse` object, which contains the transcription results.
        
        """
    
        if 'buffer' in source and 'mimetype' not in source:
            raise DeepgramApiError(
                'Mimetype must be provided if the source is bytes',
                http_library_error=None,
            )
        payload = cast(
            Union[bytes, Dict],
            source.get('buffer', {'url': source.get('url')})
        )
        content_type = cast(str, source.get('mimetype', 'application/json'))
        return _sync_request(
            f'{self._root}{_make_query_string(self.transcription_options)}',
            self.options, method='POST', payload=payload,
            headers={'Content-Type': content_type},
            timeout=timeout
        )


class LiveTranscription:
    """
    This class allows you to perform live transcription by connecting to Deepgram's Transcribe Streaming API.
    It takes in options for the transcription job, and a callback function to handle events.

    """

    _root = "/listen"
    MESSAGE_TIMEOUT = 1.0

    def __init__(self, options: Options,
                 transcription_options: LiveOptions, endpoint) -> None:
        """
        The __init__ function is called when an instance of the class is created.
        It initializes all of the attributes that are part of the object, and can be
        accessed using "self." notation. In this case, it sets up a list to store any
        messages received from Transcribe Streaming.
        
        :param options:Options: Used to Pass the options for the transcription job.
        :param transcription_options:LiveOptions: Used to Pass in the configuration for the transcription job.
        :return: None.
        
        """

        self.options = options
        if endpoint is not None:
            self._root = endpoint
        self.transcription_options = transcription_options
        self.handlers: List[Tuple[LiveTranscriptionEvent, EventHandler]] = []
        # all received messages
        self.received: List[Union[LiveTranscriptionResponse, Metadata]] = []
        # is the transcription job done?
        self.done = False
        self._socket = cast(websockets.client.WebSocketClientProtocol, None)
        self._queue: asyncio.Queue[Tuple[bool, Any]] = asyncio.Queue()

    async def __call__(self) -> 'LiveTranscription':
        """
        The __call__ function is a special method that allows the object to be called
        as a function. In this case, it is used to connect the client and start the
        transcription process. It returns itself after starting so that operations can
        be chained.
        
        :return: The object itself.
        
        """
        self._socket = await _socket_connect(
            f'{self._root}{_make_query_string(self.transcription_options)}',
            self.options
        )
        asyncio.create_task(self._start())
        return self

    async def _start(self) -> None:
        """
        The _start function is the main function of the LiveTranscription class.
        It is responsible for creating a websocket connection to Deepgram Transcribe,
        and then listening for incoming messages from that socket. It also sends any 
        messages that are in its queue (which is populated by other functions). The 
        _start function will run until it receives a message with an empty transcription, 
        at which point it will close the socket and return.
        
        :return: None.

        """

        asyncio.create_task(self._receiver())
        self._ping_handlers(LiveTranscriptionEvent.OPEN, self)

        while not self.done:
            try:
                incoming, body = await asyncio.wait_for(self._queue.get(), self.MESSAGE_TIMEOUT)
            except asyncio.TimeoutError:
                if self._socket.closed:
                    self.done = True
                    break
                continue

            if incoming:
                try:
                    parsed: Union[
                        LiveTranscriptionResponse, Metadata
                    ] = json.loads(body)
                    # Stream-ending response is only a metadata object
                    self._ping_handlers(
                        LiveTranscriptionEvent.TRANSCRIPT_RECEIVED,
                        parsed
                    )
                    self.received.append(parsed)
                    if 'sha256' in parsed: 
                        self.done = True
                except json.decoder.JSONDecodeError:
                    self._ping_handlers(
                        LiveTranscriptionEvent.ERROR,
                        f'Couldn\'t parse response JSON: {body}'
                    )
            else:
                await self._socket.send(body)
        self._ping_handlers(
            LiveTranscriptionEvent.CLOSE,
            self._socket.close_code
        )

    async def _receiver(self) -> None:
        """
        The _receiver function is a coroutine that receives messages from the socket and puts them in a queue.
        It is started by calling start_receiver() on an instance of AsyncSocket. It runs until the socket is closed,
        or until an exception occurs.
        
        :return: None.

        """

        while not self.done:
            try:
                body = await self._socket.recv()
                self._queue.put_nowait((True, body))
            except websockets.exceptions.ConnectionClosedOK:
                await self._queue.join()
                self.done = True # socket closed, will terminate on next loop

    def _ping_handlers(self, event_type: LiveTranscriptionEvent,
                       body: Any) -> None:
        """
        The _ping_handlers function is a callback that is called when the
        transcription service sends a ping event.  It calls all of the functions
        in self.handlers, which are registered by calling add_ping_handler().
        
        :param event_type:LiveTranscriptionEvent: Used to Determine if the function should be called.
        :param body:Any: Used to Pass the event data to the handler function.
        :return: The list of handlers for the event type.

        """
        
        for handled_type, func in self.handlers:
            if handled_type is event_type:
                if inspect.iscoroutinefunction(func):
                    asyncio.create_task(cast(Awaitable[None], func(body)))
                else:
                    func(body)

    # Public

    def register_handler(self, event_type: LiveTranscriptionEvent,
                         handler: EventHandler) -> None:
        """Adds an event handler to the transcription client."""

        self.handlers.append((event_type, handler))

    # alias for incorrect method name in v0.1.x
    def registerHandler(self, *args, **kwargs):
        warn(
            (
                "This method name is deprecated, "
                "and will be removed in the future - "
                "use `register_handler`."
            ),
            DeprecationWarning
        )
        return self.register_handler(*args, **kwargs)

    def deregister_handler(self, event_type: LiveTranscriptionEvent,
                           handler: EventHandler) -> None:
        """Removes an event handler from the transcription client."""

        self.handlers.remove((event_type, handler))

    # alias for incorrect method name in v0.1.x
    def deregisterHandler(self, *args, **kwargs):
        warn(
            (
                "This method name is deprecated, "
                "and will be removed in the future - "
                "use `deregister_handler`."
            ),
            DeprecationWarning
        )
        return self.deregister_handler(*args, **kwargs)

    def send(self, data: Union[bytes, str]) -> None:
        """Sends data to the Deepgram endpoint."""

        self._queue.put_nowait((False, data))

    def configure(self, config: ToggleConfigOptions) -> None:
        """Sends messages to configure transcription parameters mid-stream."""
        self._queue.put_nowait((False, json.dumps({
            "type": "Configure",
            "processors": config
        })))

    def keep_alive(self) -> None:
        """Keeps the connection open when no audio data is being sent."""
        self._queue.put_nowait((False, json.dumps({"type": "KeepAlive"})))

    async def finish(self) -> None:
        """Closes the connection to the Deepgram endpoint,
        waiting until ASR is complete on all submitted data."""

        self.send(json.dumps({"type": "CloseStream"}))  # Set message for "data is finished sending"
        while not self.done:
            await asyncio.sleep(0.1)

    @property
    def event(self) -> Enum:
        """An enum representing different possible transcription events
        that handlers can be registered against."""

        return cast(Enum, LiveTranscriptionEvent)


class Transcription:
    """
    This is the Transcription class. It provides two async methods, prerecorded and live, that
    return transcription responses for audio files and live audio streams, respectively.

    """

    def __init__(self, options: Options) -> None:
        self.options = options

    async def prerecorded(
        self, source: TranscriptionSource,
        options: PrerecordedOptions = None,
        endpoint = "/listen",
        timeout: float = None,
        **kwargs
    ) -> PrerecordedTranscriptionResponse:
        """Retrieves a transcription for an already-existing audio file,
        local or web-hosted."""
        if options is None:
            options = {}
        full_options = cast(PrerecordedOptions, {**options, **kwargs})
        return await PrerecordedTranscription(
            self.options, full_options, endpoint
        )(source, timeout=timeout)

    def sync_prerecorded(
        self, source: TranscriptionSource,
        options: PrerecordedOptions = None,
        endpoint = "/listen",
        timeout: float = None,
        **kwargs
    ) -> PrerecordedTranscriptionResponse:
        """Retrieves a transcription for an already-existing audio file,
        local or web-hosted."""
        if options is None:
            options = {}
        full_options = cast(PrerecordedOptions, {**options, **kwargs})
        return SyncPrerecordedTranscription(
            self.options, full_options, endpoint
        )(source, timeout=timeout)

    async def live(
        self, options: LiveOptions = None, endpoint = "/listen", **kwargs
    ) -> LiveTranscription:
        """Provides a client to send raw audio data to be transcribed."""
        if options is None:
            options = {}
        full_options = cast(LiveOptions, {**options, **kwargs})
        return await LiveTranscription(
            self.options, full_options, endpoint
        )()
