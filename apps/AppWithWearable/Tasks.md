### Tasks

- [ ] It shouldn't require to reconnect every time that you open the app, it should load `ConnectDeviceWidget` and in there listen/reconnect to the device.
- [ ] Device disconnected, display dialog to user asking to reconnect, or take the user back to `find_devices` page.
- [ ] Settings bottom sheet, improve way of handling `***` blurring of api keys, as if you save it while is blurred with *, it sets the key to that value, and you have to set them again
- [ ] [iOS] memories and chat page on the bottom do not have the blurred colors pattern, but plain primary color
- [ ] Improve structured memory results performance by sending n previous memories as part of the structuring but as context, not as part of the structure, so that if there's some reference to a person, and then you use a pronoun, the LLM understands what you are referring to.
- [ ] Migrate MemoryRecord from SharedPreferences to sqlite
- [ ] Implement [similarity search](https://www.pinecone.io/learn/vector-similarity/) locally
  - [ ] Use from the AppStandalone `_ragContext` function as a baseline for creating the query embedding.
  - [ ] When a memory is created, compute the vector embedding and store it locally.
  - [ ] When the user sends a question in the chat, extract from the AppStandalone the `function_calling` that determines if the message requires context, if that's the case, retrieve the top 10 most similar vectors ~~ For an initial version we can read all memories from sqlite or SharedPreferences, and compute the formula between the query and each vector.
  - [ ] Use that as context, and ask to the LLM. Retrieve the prompt from the AppStandalone.
- [ ] Settings Deepgram + openAI key are forced to be set
- [ ] In case an API key fails, either Deepgram WebSocket connection fails, or GPT requests, let the user know the error message, either has no more credits, api key is invalid, etc.
- [ ] Improve connected device page UI, including transcription text, and when memory creates after 30 seconds, let the user know
- [ ] Structure the memory asking JSON output `{"title", "summary"}`, in that way we can have better parsed data.
- [ ] Test/Implement [speaker diarization](https://developers.deepgram.com/docs/diarization) to recognize multiple speakers in transcription, use that for better context when creating the structured memory.
- [ ] Better `AppWithWerable`  folders structure.
- [ ] Define flutter code style rules.