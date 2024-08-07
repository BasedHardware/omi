1 import hashlib
2 import random
3 import threading
4 import uuid
5 from typing import Union
6 
7 from fastapi import APIRouter, Depends, HTTPException
8 
9 import database.memories as memories_db
10 from database.vector import upsert_vector, delete_vector, upsert_vectors
11 from models.memory import *
12 from models.plugin import Plugin
13 from models.transcript_segment import TranscriptSegment
14 from routers.plugins import get_plugins_data
15 from utils import auth
16 from utils.llm import generate_embedding, get_transcript_structure, get_plugin_result, summarize_open_glass
17 from utils.location import get_google_maps_location
18 from utils.plugins import trigger_external_integrations
19 
20 router = APIRouter()
21 
22 
23 def _process_memory(uid: str, language_code: str, memory: Union[Memory, CreateMemory], force_process: bool = False):
24     transcript = memory.get_transcript()
25 
26     photos = []
27     if memory.photos:
28         structured: Structured = summarize_open_glass(memory.photos)
29         photos = memory.photos
30         memory.photos = []  # Clear photos to avoid saving them in the memory
31     else:
32         structured: Structured = get_transcript_structure(transcript, memory.started_at, language_code, force_process)
33 
34     discarded = structured.title == ''
35 
36     if isinstance(memory, CreateMemory):
37         memory = Memory(
38             id=str(uuid.uuid4()),
39             uid=uid,
40             structured=structured,
41             **memory.dict(),
42             created_at=datetime.utcnow(),
43             transcript=transcript,
44             discarded=discarded,
45             deleted=False,
46         )
47         if photos:
48             memories_db.store_memory_photos(uid, memory.id, photos)
49     else:
50         memory.structured = structured
51         memory.discarded = discarded
52 
53     if not discarded:
54         structured_str = str(structured)
55         vector = generate_embedding(structured_str)
56         upsert_vector(uid, memory, vector)
57 
58         plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
59         filtered_plugins = [plugin for plugin in plugins if plugin.works_with_memories() and plugin.enabled]
60         threads = []
61 
62         def execute_plugin(plugin):
63             if result := get_plugin_result(transcript, plugin).strip():
64                 memory.plugins_results.append(PluginResult(plugin_id=plugin.id, content=result))
65 
66         for plugin in filtered_plugins:
67             threads.append(threading.Thread(target=execute_plugin, args=(plugin,)))
68 
69         [t.start() for t in threads]
70         [t.join() for t in threads]
71 
72     memories_db.upsert_memory(uid, memory.dict())
73     return memory
74 
75 
76 @router.post("/v1/memories", response_model=CreateMemoryResponse, tags=['memories'])
77 def create_memory(
78         create_memory: CreateMemory, trigger_integrations: bool, language_code: Optional[str] = None,
79         uid: str = Depends(auth.get_current_user_uid)
80 ):
81     geolocation = create_memory.geolocation
82     if geolocation and not geolocation.google_place_id:
83         create_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)
84 
85     if not language_code:  # not breaking change
86         language_code = create_memory.language
87     else:
88         create_memory.language = language_code
89 
90     memory = _process_memory(uid, language_code, create_memory)
91     if not trigger_integrations:
92         return CreateMemoryResponse(memory=memory, messages=[])
93 
94     messages = trigger_external_integrations(uid, memory)
95 
96     # Google Calendar integration
97     google_calendar_url = 'https://your-plugin-url.com/google_calendar'
98     google_calendar_response = requests.post(google_calendar_url, json=memory.dict())
99     if google_calendar_response.status_code == 200:
100         google_calendar_message = google_calendar_response.json().get('message', '')
101         if google_calendar_message:
102             messages.append(google_calendar_message)
103 
104     return CreateMemoryResponse(memory=memory, messages=messages)
105 
106 
107 @router.post('/v1/memories/{memory_id}/reprocess', response_model=Memory, tags=['memories'])
108 def reprocess_memory(
109         memory_id: str, language_code: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
110 ):
111     memory = memories_db.get_memory(uid, memory_id)
112     if memory is None:
113         raise HTTPException(status_code=404, detail="Memory not found")
114     memory = Memory(**memory)
115     if not language_code:  # not breaking change
116         language_code = memory.language or 'en'
117 
118     return _process_memory(uid, language_code, memory, force_process=True)
119 
120 
121 @router.get('/v1/memories', response_model=List[Memory], tags=['memories'])
122 def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
123     print('get_memories', uid, limit, offset)
124     return memories_db.get_memories(uid, limit, offset, include_discarded=True)
125 
126 
127 def _get_memory_by_id(uid: str, memory_id: str):
128     memory = memories_db.get_memory(uid, memory_id)
129     if memory is None or memory.get('deleted', False):
130         raise HTTPException(status_code=404, detail="Memory not found")
131     return memory
132 
133 
134 @router.get("/v1/memories/{memory_id}", response_model=Memory, tags=['memories'])
135 def get_memory_by_id(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
136     return _get_memory_by_id(uid, memory_id)
137 
138 
139 @router.get("/v1/memories/{memory_id}/photos", response_model=List[MemoryPhoto], tags=['memories'])
140 def get_memory_photos(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
141     _get_memory_by_id(uid, memory_id)
142     return memories_db.get_memory_photos(uid, memory_id)
143 
144 
145 @router.delete("/v1/memories/{memory_id}", status_code=204, tags=['memories'])
146 def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
147     memories_db.delete_memory(uid, memory_id)
148     delete_vector(memory_id)
149     return {"status": "Ok"}
150 
151 
152 # ************************************************
153 # ************ Migrate Local Memories ************
154 # ************************************************
155 
156 
157 def _get_structured(memory: dict):
158     category = memory['structured']['category']
159     if category not in CategoryEnum.__members__:
160         category = 'other'
161     emoji = memory['structured'].get('emoji')
162     try:
163         emoji = emoji.encode('latin1').decode('utf-8')
164     except:
165         emoji = random.choice(['🧠', '🎉'])
166 
167     return Structured(
168         title=memory['structured']['title'],
169         overview=memory['structured']['overview'],
170         emoji=emoji,
171         category=CategoryEnum[category],
172         action_items=[
173             ActionItem(description=description, completed=False) for description in
174             memory['structured']['actionItems']
175         ],
176         events=[
177             Event(
178                 title=event['title'],
179                 description=event['description'],
180                 start=datetime.fromisoformat(event['startsAt']),
181                 duration=event['duration'],
182                 created=False,
183             ) for event in memory['structured']['events']
184         ],
185     )
186 
187 
188 def _get_geolocation(memory: dict):
189     geolocation = memory.get('geoLocation', {})
190     if geolocation and geolocation.get('googlePlaceId'):
191         geolocation_obj = Geolocation(
192             google_place_id=geolocation['googlePlaceId'],
193             latitude=geolocation['latitude'],
194             longitude=geolocation['longitude'],
195             address=geolocation['address'],
196             location_type=geolocation['locationType'],
197         )
198     else:
199         geolocation_obj = None
200     return geolocation_obj
201 
202 
203 def generate_uuid4_from_seed(seed):
204     # Use SHA-256 to hash the seed
205     hash_object = hashlib.sha256(seed.encode('utf-8'))
206     hash_digest = hash_object.hexdigest()
207     return uuid.UUID(hash_digest[:32])
208 
209 
210 def upload_memory_vectors(uid: str, memories: List[Memory]):
211     if not memories:
212         return
213     vectors = [generate_embedding(str(memory.structured)) for memory in memories]
214     upsert_vectors(uid, vectors, memories)
215 
216 
217 @router.post('/v1/migration/memories', tags=['v1'])
218 def migrate_local_memories(memories: List[dict], uid: str = Depends(auth.get_current_user_uid)):
219     if not memories:
220         return {'status': 'ok'}
221     memories_vectors = []
222     db_batch = memories_db.get_memories_batch_operation()
223     for i, memory in enumerate(memories):
224         if memory.get('photos'):
225             continue  # Ignore openGlass memories for now
226 
227         structured_obj = _get_structured(memory)
228         # print(structured_obj)
229         if not memory['transcriptSegments'] and memory['transcript']:
230             memory['transcriptSegments'] = [{'text': memory['transcript']}]
231 
232         memory_obj = Memory(
233             id=str(generate_uuid4_from_seed(f'{uid}-{memory["createdAt"]}')),
234             uid=uid,
235             structured=structured_obj,
236             created_at=datetime.fromisoformat(memory['createdAt']),
237             started_at=datetime.fromisoformat(memory['startedAt']) if memory['startedAt'] else None,
238             finished_at=datetime.fromisoformat(memory['finishedAt']) if memory['finishedAt'] else None,
239             discarded=memory['discarded'],
240             transcript_segments=[
241                 TranscriptSegment(
242                     text=segment['text'],
243                     start=segment.get('start', 0),
244                     end=segment.get('end', 0),
245                     speaker=segment.get('speaker', 'SPEAKER_00'),
246                     is_user=segment.get('is_user', False),
247                 ) for segment in memory['transcriptSegments'] if segment.get('text', '')
248             ],
249             plugins_results=[
250                 PluginResult(plugin_id=result.get('pluginId'), content=result['content'])
251                 for result in memory['pluginsResponse']
252             ],
253             # photos=[
254             #     MemoryPhoto(description=photo['description'], base64=photo['base64']) for photo in memory['photos']
255             # ],
256             geolocation=_get_geolocation(memory),
257             deleted=False,
258         )
259         memories_db.add_memory_to_batch(db_batch, uid, memory_obj.dict())
260         print(len(str(memory_obj.dict())))
261 
262         if not memory_obj.discarded:
263             memories_vectors.append(memory_obj)
264 
265         if i % 10 == 0:
266             threading.Thread(target=upload_memory_vectors, args=(uid, memories_vectors[:])).start()
267             memories_vectors = []
268 
269         if i % 20 == 0:
270             db_batch.commit()
271             db_batch = memories_db.get_memories_batch_operation()
272 
273     db_batch.commit()
274     threading.Thread(target=upload_memory_vectors, args=(uid, memories_vectors[:])).start()
275     return {}
276 
277 # Future<String> dailySummaryNotifications(List<Memory> memories) async {
278 #   var msg = 'There were no memories today, don\'t forget to wear your Friend tomorrow 😁';
279 #   if (memories.isEmpty) return msg;
280 #   if (memories.where((m) => !m.discarded).length <= 1) return msg;
281 #   var str = SharedPreferencesUtil().givenName.isEmpty ? 'the user' : SharedPreferencesUtil().givenName;
282 #   var prompt = '''
283 #   The following are a list of $str\'s memories from today, with the transcripts with its respective structuring, that $str had during his day.
284 #   $str wants to get a summary of the key action items he has to take based on his today's memories.
285 #
286 #   Remember $str is busy so this has to be very efficient and concise.
287 #   Respond in at most 50 words.
288 #
289 #   Output your response in plain text, without markdown.
290 #   ```
291 #   ${Memory.memoriesToString(memories, includeTranscript: true)}
292 #   ```
293 #   ''';
294 #   debugPrint(prompt);
295 #   var result = await executeGptPrompt(prompt);
296 #   debugPrint('dailySummaryNotifications result: $result');
297 #   return result.replaceAll('```', '').trim();
298 # }
299 
