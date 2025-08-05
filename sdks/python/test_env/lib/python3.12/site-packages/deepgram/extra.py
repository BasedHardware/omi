import warnings

from ._types import PrerecordedTranscriptionResponse, Options
from ._enums import Caption

class Extra:
    """
    Extra post-processing to transform raw Deepgram responses to conveniently-formatted outputs.
    """

    def __init__(self, options: Options) -> None:
        self.options = options

    """
    Helper function to transform a seconds mark into a formatted timestamp.
    I.e. 6.564 -> 00:00:06,564

    :param seconds:float
    :param separator:str
    :return Formatted timestamp string.
    """
    def _format_timestamp(self, seconds: float, separator: str):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"

    """
    Transform a Deepgram PrerecordedTranscriptionResponse into a set of captions.

    :param response:PrerecordedTranscriptionResponse: Deepgram response.
    :param format:Caption: The caption format enum (SRT or WebVTT).
    :param line_length:int: Number of words in each caption line.
    :return A string containing the response's captions.
    """
    def _to_caption(
            self,
            response: PrerecordedTranscriptionResponse,
            format: Caption,
            line_length: int,
        ):
        if "utterances" in response["results"]:
            utterances = response["results"]["utterances"]
        else:
            warnings.warn(
                "Enabling the Utterances feature is strongly recommended for captioning. Utterances allow "
                "captions to be delimited by pauses. Add request parameter `'utterances': True`."
            )
            utterances = response["results"]["channels"][0]["alternatives"]
        captions = []
        line_counter = 1
        if format is Caption.WEBVTT:
            captions.append("WEBVTT")
        for utt_index, utt in enumerate(utterances):
            words = utterances[utt_index]["words"]
            word_text = "punctuated_word" if "punctuated_word" in words[0] else "word"
            for i in range(0, len(words), line_length):
                start_time = words[i]["start"]
                end_index = min(len(words) - 1, i + line_length - 1)
                end_time = words[end_index]["end"]
                text = " ".join([w[word_text] for w in words[i:end_index + 1]])
                separator = "," if format is Caption.SRT else '.'
                prefix = "" if format is Caption.SRT else "- "
                caption = (
                    f"{line_counter}\n"
                    f"{self._format_timestamp(start_time, separator)} --> "
                    f"{self._format_timestamp(end_time, separator)}\n"
                    f"{prefix}{text}"
                )
                captions.append(caption)
                line_counter += 1
        return "\n\n".join(captions)

    """
    Transform a Deepgram PrerecordedTranscriptionResponse into SRT captions.

    :param response:PrerecordedTranscriptionResponse: Deepgram response.
    :param line_length:int: Number of words in each caption line. Defaults to 8.
    :param readable:bool: If the captions should be printed in a human-readable format,
        instead of with newline characters. Defaults to True.
    :return Nothing if readable=True, string of captions if readable=False.
    """
    def to_SRT(
            self, 
            response: PrerecordedTranscriptionResponse,
            line_length: int=8,
            readable: bool=True
        ):
        captions = self._to_caption(response, Caption.SRT, line_length)
        if not readable:
            return captions
        print(captions)

    """
    Transform a Deepgram PrerecordedTranscriptionResponse into WebVTT captions.

    :param response:PrerecordedTranscriptionResponse: Deepgram response.
    :param line_length:int: Number of words in each caption line. Defaults to 8.
    :param readable:bool: If the captions should be printed in a human-readable format,
        instead of with newline characters. Defaults to True.
    :return Nothing if readable=True, string of captions if readable=False.
    """
    def to_WebVTT(
            self,
            response: PrerecordedTranscriptionResponse,
            line_length: int=8,
            readable: bool=True
        ):
        captions = self._to_caption(response, Caption.WEBVTT, line_length)
        if not readable:
            return captions
        print(captions)
