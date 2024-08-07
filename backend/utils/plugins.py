1 import threading
2 from datetime import datetime
3 from typing import List, Optional
4 
5 import requests
6 
7 from database.chat import add_plugin_message
8 from models.memory import Memory
9 from models.plugin import Plugin
10 from models.transcript_segment import TranscriptSegment
11 from utils.redis_utils import get_enabled_plugins, get_plugin_reviews
12 
13 
14 def get_plugin_by_id(plugin_id: str) -> Optional[Plugin]:
15     if not plugin_id:
16         return None
17     plugins = get_plugins_data('', include_reviews=False)
18     return next((p for p in plugins if p.id == plugin_id), None)
19 
20 
21 def weighted_rating(plugin):
22     C = 3.0  # Assume 3.0 is the mean rating across all plugins
23     m = 5  # Minimum number of ratings required to be considered
24     R = plugin.rating_avg or 0
25     v = plugin.rating_count or 0
26     return (v / (v + m) * R) + (m / (v + m) * C)
27 
28 
29 def get_plugins_data(uid: str, include_reviews: bool = False) -> List[Plugin]:
30     # print('get_plugins_data', uid, include_reviews)
31     response = requests.get('https://raw.githubusercontent.com/BasedHardware/Friend/main/community-plugins.json')
32     if response.status_code != 200:
33         return []
34     user_enabled = set(get_enabled_plugins(uid))
35     print('get_plugins_data, user_enabled', user_enabled)
36     data = response.json()
37     plugins = []
38     for plugin in data:
39         plugin_dict = plugin
40         plugin_dict['enabled'] = plugin['id'] in user_enabled
41         if include_reviews:
42             reviews = get_plugin_reviews(plugin['id'])
43             sorted_reviews = sorted(reviews.values(), key=lambda x: datetime.fromisoformat(x['rated_at']), reverse=True)
44             rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if sorted_reviews else None
45             plugin_dict['reviews'] = []
46             plugin_dict['user_review'] = reviews.get(uid)
47             plugin_dict['rating_avg'] = rating_avg
48             plugin_dict['rating_count'] = len(sorted_reviews)
49         plugins.append(Plugin(**plugin_dict))
50     if include_reviews:
51         plugins = sorted(plugins, key=weighted_rating, reverse=True)
52 
53     return plugins
54 
55 
56 def trigger_external_integrations(uid: str, memory: Memory) -> list:
57     plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
58     filtered_plugins = [plugin for plugin in plugins if plugin.triggers_on_memory_creation() and plugin.enabled]
59     if not filtered_plugins:
60         return []
61 
62     threads = []
63     results = {}
64 
65     def _single(plugin: Plugin):
66         if not plugin.external_integration.webhook_url:
67             return
68 
69         memory_dict = memory.dict()
70         memory_dict['created_at'] = memory_dict['created_at'].isoformat()
71         memory_dict['started_at'] = memory_dict['started_at'].isoformat() if memory_dict['started_at'] else None
72         memory_dict['finished_at'] = memory_dict['finished_at'].isoformat() if memory_dict['finished_at'] else None
73         url = plugin.external_integration.webhook_url
74         if '?' in url:
75             url += '&uid=' + uid
76         else:
77             url += '?uid=' + uid
78 
79         response = requests.post(url, json=memory_dict)
80         if response.status_code != 200:
81             print('Plugin integration failed', plugin.id, 'result:', response.content)
82             return
83 
84         print('response', response.json())
85         if message := response.json().get('message', ''):
86             results[plugin.id] = message
87 
88     for plugin in filtered_plugins:
89         threads.append(threading.Thread(target=_single, args=(plugin,)))
90 
91     [t.start() for t in threads]
92     [t.join() for t in threads]
93 
94     messages = []
95     for key, message in results.items():
96         if not message:
97             continue
98         messages.append(add_plugin_message(message, key, uid, memory.id))
99 
100     # Google Calendar integration
101     google_calendar_url = 'https://your-plugin-url.com/google_calendar'
102     google_calendar_response = requests.post(google_calendar_url, json=memory.dict())
103     if google_calendar_response.status_code == 200:
104         google_calendar_message = google_calendar_response.json().get('message', '')
105         if google_calendar_message:
106             messages.append(add_plugin_message(google_calendar_message, 'google_calendar', uid, memory.id))
107 
108     return messages
109 
110 
111 def trigger_realtime_integrations(uid: str, segments: List[TranscriptSegment]) -> dict:
112     plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
113     filtered_plugins = [plugin for plugin in plugins if plugin.triggers_realtime() and plugin.enabled]
114     if not filtered_plugins:
115         return {}
116 
117     threads = []
118     results = {}
119 
120     def _single(plugin: Plugin):
121         if not plugin.external_integration.webhook_url:
122             return
123 
124         url = plugin.external_integration.webhook_url
125         if '?' in url:
126             url += '&uid=' + uid
127         else:
128             url += '?uid=' + uid
129 
130         response = requests.post(url, json=[segment.dict() for segment in segments])
131         if response.status_code != 200:
132             print('Plugin integration failed', plugin.id, 'result:', response.content)
133             return
134 
135         print('response', response.json())
136         if message := response.json().get('message', ''):
137             results[plugin.id] = message
138 
139     for plugin in filtered_plugins:
140         threads.append(threading.Thread(target=_single, args=(plugin,)))
141 
142     [t.start() for t in threads]
143     [t.join() for t in threads]
144     messages = []
145     for key, message in results.items():
146         if not message:
147             continue
148         messages.append(add_plugin_message(message, key, uid))
149     return messages
150 
