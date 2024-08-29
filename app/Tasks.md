### Tasks

- [X] It shouldn't require to reconnect every time that you open the app, it should  
  load `ConnectDeviceWidget` and in there listen/reconnect to the device.
- [X] Device disconnected, display dialog to user asking to reconnect, or take the user back  
  to `find_devices` page.
- [x] Settings bottom sheet, improve way of handling `***` blurring of api keys, as if you save it  
  while is blurred with *, it sets the key to that value, and you have to set them again
- [X] [iOS] memories and chat page on the bottom do not have the blurred colors pattern, but plain  
  primary color
- [ ] Improve structured memory results performance by sending n previous memories as part of the  
  structuring but as context, not as part of the structure, so that if there's some reference to a  
  person, and then you use a pronoun, the LLM understands what you are referring to.
- [ ] Migrate MemoryRecord from SharedPreferences to sqlite
- [X] Implement [similarity search](https://www.pinecone.io/learn/vector-similarity/) locally
    - [X] Use from the AppStandalone `_ragContext` function as a baseline for creating the query  
      embedding.
    - [X] When a memory is created, compute the vector embedding and store it locally.
    - [X] When the user sends a question in the chat, extract from the AppStandalone  
      the `function_calling` that determines if the message requires context, if that's the case,  
      retrieve the top 10 most similar vectors ~~ For an initial version we can read all memories  
      from sqlite or SharedPreferences, and compute the formula between the query and each vector.
    - [X] Use that as context, and ask to the LLM. Retrieve the prompt from the AppStandalone.
    - [ ] Improve function call way of parsing the text sent to the RAG, GPT should format the input
      better for RAG to retrieve better context.
- [X] Settings Deepgram + openAI key are forced to be set
- [ ] In case an API key fails, either Deepgram WebSocket connection fails, or GPT requests, let
  the user know the error message, either has no more credits, api key is invalid, etc.
- [ ] Improve connected device page UI, including transcription text, and when memory creates
  after  
  30 seconds, let the user know
- [ ] Structure the memory asking JSON output `{"title", "summary"}`, in that way we can have
  better parsed data.
- [x] Test/Implement [speaker diarization](https://developers.deepgram.com/docs/diarization) to  
  recognize multiple speakers in transcription, use that for better context when creating the  
  structured memory.
- [x] Better `AppWithWerable` folders structure.
- [ ] Define flutter code style rules.
- [ ] Include documentation on how to run `AppWithWearable`.
- [ ] If only 1 speaker, set memory prompt creation, explain those are your thoughts, not a
  conversation, also, remove Speaker $i in transcript.
- [ ] Allow users who don't have a GCP bucket to store their recordings locally.
- [ ] Improve recordings audio player.

---  

- [x] Multilanguage option, implement settings selector, and use that for the deepgram websocket  
  creation
- [x] Option for storing your transcripts somewhere in the cloud, user inputs their own GCP
  storage  
  bucket + auth key, and the files are uploaded there + a reference is stored in the MemoryRecord  
  object.
    - [ ] `createWavFile` remove empty sounds without words, and saves that fixed file.

- [ ] ~~ (Idea) Detect a keyword or special order e.g. "Hey Friend" (but not so generic) and  
  triggers a prompt execution + response. This would require a few hardware updates (could also be
  a  
  button on the device), and it's way bigger than it seems.
- [ ] ~~ (Idea) Store the location at which the memory was created, and have saved places, like "
  at  
  Home you were chatting about x and y"
- [ ] ~~ (Idea) Speaker detection, use something like the python  
  library [librosa](https://github.com/librosa/librosa), so that friend recognizes when is you the  
  one speaking and creates memories better considering that. Maybe even later learns to recognize  
  other people.