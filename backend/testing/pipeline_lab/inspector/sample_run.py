"""Write a synthetic corpus day, production baseline and two runs into a store root.

Everything is fictional (a Saturday in the made-up town of Lumen Bay) and follows the DESIGN store
contract, so tests and UI work never need private data. The day covers every inspector state:
kept and discarded conversations, boundary shifts, a split and a merge, discard flips, new and
missing conversations, changed summaries, tasks, memories and pushes, LLM calls with cache hits,
two unknown audio gaps, and a generated tone WAV per audio clip so the player and transcript sync work.

    python -m testing.pipeline_lab.inspector.sample_run --root /Volumes/Ephemeral/pipeline-lab-sample [--verdicts DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from testing.pipeline_lab.inspector import views
from testing.pipeline_lab.inspector.reader import (
    Reader,
    boundary_key,
    content_key,
    new_verdict_id,
    notification_key,
    summary_key,
    utc_iso,
)

DAY_ID = 'sample-2026-03-14'
DATE = '2026-03-14'
TIMEZONE = 'America/Los_Angeles'
UTC_OFFSET_H = -7  # PDT on this date
RUN_ID = 'sample-20260314-summary-v7'
MAIN_RUN_ID = 'sample-20260314-main'
OWNER = 'Sam'
GAPS = (('12:40', '13:30'), ('16:05', '16:50'))
SPEAKER_TONES = {'Sam': 220.0, 'Juniper': 330.0, 'Captain Ferro': 262.0, 'Otto': 294.0, 'Mira': 392.0}
DEFAULT_TONE = 349.0

# Each spec is one production conversation (plus how the replay differs). Lines are (speaker, text).
SPECS: list[dict[str, Any]] = [
    dict(
        t='07:12',
        dur=4,
        emoji='☕',
        cat='personal',
        title='Morning coffee and the tide table',
        overview='Sam and Juniper planned the day around the low tide at 11:40 and agreed to take the long way to the harbour.',
        lines=[
            ('Juniper', 'Low tide is at eleven forty today, so the tidepools will be open late morning.'),
            ('Sam', 'Then we can do the harbour walk after the rocket club rehearsal.'),
            ('Juniper', 'Take the long way past the lighthouse, the cliff path is still muddy.'),
            ('Sam', 'Good call. I will bring the small thermos.'),
            ('Juniper', 'And the field guide, the one with the purple urchins on the cover.'),
        ],
        tasks=['Bring the field guide to the harbour walk'],
        memories=[('Juniper prefers the long route past the lighthouse when the cliff path is muddy', 'interesting')],
    ),
    dict(
        t='07:48',
        dur=1.5,
        emoji='📻',
        cat='other',
        title='',
        overview='',
        discarded=True,
        discard_reason='no_meaningful_content',
        lines=[('Sam', 'Where did the kettle go.'), ('Speaker 2', '...and now the shipping forecast for Lumen Bay...')],
    ),
    dict(
        t='08:20',
        dur=6,
        emoji='🗼',
        cat='work',
        title='Lighthouse co-op volunteer roster',
        overview='Captain Ferro asked Sam to cover two lamp-room shifts next week and to update the shared roster before Monday.',
        lines=[
            ('Captain Ferro', 'We are short two people on the lamp-room shifts next Tuesday and Thursday.'),
            ('Sam', 'I can take Tuesday evening. Thursday is harder because of choir.'),
            ('Captain Ferro', 'Could you swap with Otto? He owes you one from the storm night.'),
            ('Sam', 'I will ask him today and update the roster before Monday.'),
            ('Captain Ferro', 'Perfect. And remind people the lens cloth goes back in the brass tin.'),
        ],
        tasks=['Update the lighthouse roster before Monday', 'Ask Otto to swap the Thursday lamp-room shift'],
        memories=[('Sam volunteers for evening lamp-room shifts at the lighthouse co-op', 'work')],
        variant='summary',
        r_title='Lighthouse co-op: two lamp-room shifts to cover',
        r_overview='Captain Ferro needs cover for Tuesday and Thursday lamp-room shifts. Sam takes Tuesday evening, will ask Otto to swap Thursday, and updates the roster before Monday.',
    ),
    dict(
        t='09:05',
        dur=9,
        emoji='🥖',
        cat='work',
        title='Bakery supplier call',
        overview='Otto and Sam reviewed the spring flour order, moved the cardamom delivery to Friday, and discussed a rye starter for the market stall.',
        lines=[
            ('Otto', 'The mill can do twelve sacks of the stone-ground flour, but not before the twentieth.'),
            ('Sam', 'That works if the cardamom arrives on Friday instead of Wednesday.'),
            ('Otto', 'I will call them back about the cardamom. Do you still want the rye starter?'),
            ('Sam', 'Yes, half a kilo, we want to test a dark rye for the market stall.'),
            ('Otto', 'I can bring it Thursday when I swap the lighthouse shift with you.'),
            ('Sam', 'Deal. Send me the invoice so I can pay it before the end of the month.'),
        ],
        tasks=['Pay the flour invoice before the end of the month', 'Confirm the cardamom delivery for Friday'],
        memories=[('Sam and Otto plan a dark rye loaf for the Saturday market stall', 'work')],
        variant='tasks',
        r_tasks=[
            'Pay the stone-ground flour invoice before the end of the month',
            'Collect the rye starter from Otto on Thursday',
        ],
    ),
    dict(
        t='09:40',
        dur=2,
        emoji='🚌',
        cat='personal',
        title='Bus stop small talk',
        overview='A neighbour mentioned the number 4 bus now runs every twenty minutes on weekends.',
        lines=[
            ('Speaker 2', 'They changed the number four, it comes every twenty minutes on weekends now.'),
            ('Sam', 'Oh nice, that helps for the market.'),
        ],
        variant='flip_discard',
        r_discard_reason='low_content',
    ),
    dict(
        t='10:10',
        dur=12,
        emoji='🚀',
        cat='hobby',
        title='Rocket club launch rehearsal',
        overview='Mira ran the countdown checklist for the Zephyr model rocket. The parachute packing needs a second pass and the launch moves to Sunday at nine.',
        lines=[
            ('Mira', 'Okay, checklist. Igniter clip, check. Launch rail, check. Parachute packing, not great.'),
            ('Sam', 'The shock cord is twisted again. We should repack it with talc.'),
            ('Mira', 'Then we move the launch to Sunday at nine, the wind is better anyway.'),
            ('Sam', 'I will message the group and book the meadow permit.'),
            ('Mira', 'Bring the spare igniters, the blue ones, not the old red batch.'),
            ('Sam', 'Blue ones, got it. Ten, nine, eight... just kidding.'),
        ],
        tasks=['Book the meadow launch permit for Sunday 9:00', 'Message the rocket club about the new launch time'],
        memories=[('Sam co-runs the Zephyr model rocket club with Mira', 'hobby')],
        pushes=[('Launch moved', 'Zephyr launch is now Sunday 9:00. Book the meadow permit.', 'action_item_created')],
        variant='boundary',
        r_start=-95,
        r_end=170,
    ),
    dict(
        t='10:30',
        dur=3,
        emoji='⛴️',
        cat='personal',
        title='Ferry timetable question',
        overview='Sam asked a deckhand about the last ferry back from Gull Island; it leaves at 18:15 on Saturdays.',
        lines=[
            ('Sam', 'What time is the last boat back from Gull Island today?'),
            ('Speaker 2', 'Six fifteen on Saturdays, six forty-five from April.'),
        ],
        memories=[('The last Saturday ferry from Gull Island leaves at 18:15 until April', 'interesting')],
        variant='missing',
    ),
    dict(
        t='11:15',
        dur=7,
        emoji='🌱',
        cat='personal',
        title='Community garden plot with Basil',
        overview='Basil offered Sam the corner plot with better sun. They agreed to share a rain barrel and plant beans along the fence.',
        lines=[
            ('Speaker 2', 'The corner plot gets sun until five, you should take it.'),
            ('Sam', 'Then we could share the rain barrel between our plots.'),
            ('Speaker 2', 'Beans along the fence, squash in the middle, like last year.'),
            ('Sam', 'Last year the squash ate everything. Let us do fewer this time.'),
        ],
        memories=[
            ('Sam has a plot at the Lumen Bay community garden', 'personal'),
            ('Basil grows beans along the garden fence every spring', 'interesting'),
        ],
        variant='memories',
        r_memories=[
            ('Sam has the sunny corner plot at the Lumen Bay community garden', 'personal'),
            ('Sam and Basil share a rain barrel between their garden plots', 'personal'),
        ],
    ),
    dict(
        t='11:50',
        dur=1,
        emoji='🐕',
        cat='personal',
        title='',
        overview='',
        discarded=True,
        discard_reason='too_short',
        lines=[
            ('Speaker 2', 'This is Pickle, she is three, she loves everyone.'),
            ('Sam', 'Hi Pickle! What a good dog.'),
        ],
        variant='flip_keep',
        r_title='Meeting Pickle the dog',
        r_overview='A neighbour introduced their three-year-old dog, Pickle.',
        r_emoji='🐕',
    ),
    dict(
        t='12:18',
        dur=5,
        emoji='🍜',
        cat='personal',
        title='Lunch at the noodle bar',
        overview='Sam ordered the miso noodles and noted the noodle bar now closes at 15:00 on weekends.',
        lines=[
            ('Speaker 2', 'Miso noodles, extra greens? We close at three on weekends now.'),
            ('Sam', 'Yes please. Three, good to know.'),
        ],
    ),
    dict(
        t='13:32',
        dur=8,
        emoji='📚',
        cat='work',
        title='Library board meeting prep',
        overview='Sam drafted three agenda points for the library board and then took a short call about the reading-room heaters.',
        lines=[
            ('Sam', 'Agenda point one, the seed library shelf. Point two, late fees for children.'),
            ('Sam', 'Point three, the reading room heaters are still broken.'),
            ('Speaker 2', 'Hello, this is facilities about the heaters in the reading room.'),
            ('Sam', 'Great timing. Can someone look at them before Wednesday?'),
            ('Speaker 2', 'Tuesday morning, we will send someone.'),
        ],
        tasks=['Send the library board agenda', 'Confirm the heater repair on Tuesday morning'],
        variant='split',
        split_at=2,
        r_split=[
            dict(
                title='Library board agenda draft',
                overview='Sam drafted three agenda points: the seed library shelf, late fees for children, and the broken reading-room heaters.',
                tasks=['Send the library board agenda'],
            ),
            dict(
                title='Facilities call about the reading-room heaters',
                overview='Facilities will send someone to fix the reading-room heaters on Tuesday morning.',
                tasks=['Confirm the heater repair on Tuesday morning'],
                emoji='🔧',
            ),
        ],
    ),
    dict(
        t='14:10',
        dur=10,
        emoji='🎶',
        cat='hobby',
        title='Choir rehearsal notes',
        overview='The choir worked on the second verse of the harbour song; Sam needs to learn the alto line by next Thursday.',
        lines=[
            ('Speaker 2', 'Altos, the second verse comes in a bar early, again from the top.'),
            ('Sam', 'I keep missing the entrance after the key change.'),
            ('Speaker 2', 'Learn the alto line by Thursday and we will run it twice.'),
        ],
        tasks=['Learn the alto line of the harbour song by Thursday'],
        variant='merge',
    ),
    dict(
        t='14:22',
        dur=4,
        emoji='🫖',
        cat='hobby',
        title='Tea after choir',
        overview='Over tea, the choir agreed to bring cakes for the spring concert.',
        lines=[
            ('Speaker 2', 'Who is bringing cake for the spring concert?'),
            ('Sam', 'I will bring the cardamom buns, if the delivery comes Friday.'),
        ],
        tasks=['Bake cardamom buns for the spring concert'],
        variant='merged_into_prev',
        r_merge_title='Choir rehearsal and tea afterwards',
        r_merge_overview='The choir worked on the second verse of the harbour song; Sam needs the alto line by Thursday. Over tea, Sam offered cardamom buns for the spring concert.',
    ),
    dict(
        t='15:00',
        dur=6,
        emoji='🔭',
        cat='hobby',
        title='Call with Dr. Quill about the telescope',
        overview='Dr. Quill can lend the 8-inch reflector for the comet night if Sam collects it on Friday evening.',
        lane='sync',
        lines=[
            ('Speaker 2', 'The eight inch reflector is free for the comet night, if you collect it Friday.'),
            ('Sam', 'Friday evening works. Does it need the counterweight?'),
            ('Speaker 2', 'Yes, the counterweight is in the grey case, and the finder scope is loose.'),
            ('Sam', 'I will bring a screwdriver for the finder scope.'),
        ],
        tasks=['Collect the reflector telescope from Dr. Quill on Friday evening'],
        variant='transcript',
        r_lines={
            0: 'The 8-inch reflector is free for the comet night if you collect it on Friday.',
            2: 'Yes, the counterweight is in the gray case and the finder scope is a bit loose.',
        },
        r_speaker_names={'Speaker 2': 'Dr. Quill'},
    ),
    dict(
        t='15:35',
        dur=3,
        emoji='🌿',
        cat='personal',
        title='Reminder to water the seedlings',
        overview='Sam reminded themself to water the tomato seedlings tonight because tomorrow will be hot.',
        lines=[('Sam', 'Note to self, water the tomato seedlings tonight, tomorrow is going to be hot.')],
        tasks=['Water the tomato seedlings tonight'],
        pushes=[
            ('Water the seedlings', 'Tomorrow will be hot. Water the tomato seedlings tonight.', 'action_item_created')
        ],
        variant='pushes',
        r_pushes=[
            ('Seedlings tonight', 'Water the tomato seedlings before bed; tomorrow is hot.', 'action_item_created'),
            ('Heads up', 'Sunday launch at 9:00, pack the blue igniters.', 'proactive'),
        ],
    ),
    dict(
        t='16:52',
        dur=5,
        emoji='🧺',
        cat='personal',
        title='Back from the market',
        overview='Sam unpacked the market haul and noted the honey stall moves to the north row next week.',
        lines=[
            (
                'Sam',
                'Okay, leeks, the good honey, two lemons. Juniper, the honey stall moves to the north row next week.',
            ),
            ('Juniper', 'North row, near the fish man? Fine.'),
        ],
        memories=[('The honey stall at the Lumen Bay market moves to the north row', 'interesting')],
        evaluable={'boundaries': False, 'reason': 'starts right after an unknown audio gap'},
    ),
    dict(
        t='17:20',
        dur=2,
        emoji='🅿️',
        cat='personal',
        title='Parking meter mix-up',
        overview='The harbour parking meters now take cards only; Sam paid with the app.',
        lane='sync',
        lines=[
            ('Speaker 2', 'They only take cards now, the coin slots are taped over.'),
            ('Sam', 'I will use the app then, thanks.'),
        ],
        variant='new',
    ),
    dict(
        t='17:45',
        dur=11,
        emoji='🍲',
        cat='personal',
        title='Dinner plans with Juniper',
        overview='Sam and Juniper picked a fish stew for Sunday, assigned shopping, and invited Mira after the launch.',
        lines=[
            ('Juniper', 'Fish stew on Sunday? We can invite Mira after the launch.'),
            ('Sam', 'Yes. I will get the fennel and saffron, you get the fish on the way back.'),
            ('Juniper', 'And bread, the dark rye if Otto has it ready.'),
            ('Sam', 'He will not, the starter only arrives Thursday. Sourdough then.'),
        ],
        tasks=['Buy fennel and saffron for the Sunday fish stew', 'Invite Mira to dinner after the launch'],
        variant='summary_tasks',
        r_title='Sunday fish stew with Juniper and Mira',
        r_overview='Sam and Juniper chose a fish stew for Sunday. Sam buys fennel and saffron, Juniper buys the fish, and they will invite Mira after the rocket launch.',
        r_tasks=['Buy fennel and saffron for Sunday', 'Invite Mira to dinner after the launch'],
    ),
    dict(
        t='18:40',
        dur=1,
        emoji='📺',
        cat='other',
        title='',
        overview='',
        discarded=True,
        discard_reason='background_media',
        lines=[('Speaker 2', '...the contestants have sixty seconds to build a sandcastle...')],
    ),
    dict(
        t='19:15',
        dur=14,
        emoji='🎲',
        cat='personal',
        title='Board game night rules',
        overview='The group settled the trading rule dispute in Harbourmaster and agreed the loser hosts next month.',
        lines=[
            ('Juniper', 'You cannot trade lighthouses on the same turn you build them.'),
            ('Sam', 'The rulebook says any turn, page twelve.'),
            ('Mira', 'Page twelve is the expansion rules. Base game says next turn.'),
            ('Sam', 'Fine, next turn. Loser hosts next month.'),
        ],
        memories=[('The board game group plays Harbourmaster; the loser hosts next month', 'personal')],
    ),
    dict(
        t='20:05',
        dur=4,
        emoji='🥾',
        cat='personal',
        title='Packing list for the coastal hike',
        overview='Sam listed what to pack for the coastal hike: headlamp, blister kit, two litres of water and the paper map.',
        lines=[
            ('Sam', 'Headlamp, blister kit, two litres of water, the paper map because there is no signal.'),
            ('Juniper', 'And the windbreaker. The cliffs are cold even in April.'),
        ],
        tasks=['Buy a new blister kit before the coastal hike', 'Print the coastal trail map'],
        variant='tasks',
        r_tasks=[
            'Buy a blister kit before the coastal hike',
            'Print the coastal trail map',
            'Pack the windbreaker for the hike',
        ],
    ),
    dict(
        t='20:50',
        dur=3,
        emoji='💡',
        cat='work',
        title='Voice memo: tide-clock bun idea',
        overview='Sam recorded an idea for a bakery special: buns shaped like the harbour tide clock.',
        lines=[('Sam', 'Idea. Buns shaped like the harbour tide clock, glazed blue, sell them on festival weekend.')],
        memories=[('Sam wants to sell tide-clock shaped buns on the harbour festival weekend', 'work')],
    ),
    dict(
        t='21:30',
        dur=6,
        emoji='🎂',
        cat='family',
        title="Call with Wren about Dad's birthday",
        overview="Sam and Wren planned their dad's 70th: a picnic at Gull Island on the 28th, Wren books the ferry.",
        lines=[
            ('Speaker 2', 'Dad turns seventy on the twenty-eighth. Picnic on Gull Island?'),
            ('Sam', 'He would love that. Last ferry back is quarter past six, remember.'),
            ('Speaker 2', 'I will book the ferry. You bring the cake?'),
            ('Sam', 'Lemon cake, his favourite.'),
        ],
        tasks=['Bake a lemon cake for Dad on the 28th'],
        memories=[("Sam's dad turns 70 on March 28 and loves lemon cake", 'family')],
        pushes=[('Lemon cake for Dad', "Bake the lemon cake for Dad's 70th on the 28th.", 'action_item_created')],
        variant='memories_pushes',
        r_memories=[
            ("Sam's father turns 70 on March 28; his favourite cake is lemon", 'family'),
            ("Sam's sibling Wren organises family trips", 'family'),
        ],
        r_pushes=[],
    ),
    dict(
        t='22:10',
        dur=2,
        emoji='🚰',
        cat='personal',
        title='Leaky kitchen faucet',
        overview='Sam noticed the kitchen faucet drips again and wants to replace the washer.',
        lines=[('Sam', 'The kitchen tap is dripping again. Buy a washer, the small one, twelve millimetre.')],
        tasks=['Buy a 12 mm washer for the kitchen tap'],
        variant='missing',
    ),
    dict(
        t='22:40',
        dur=3,
        emoji='📓',
        cat='personal',
        title='Night journal',
        overview='Sam reflected on a full day: the launch moved, the garden plot is sorted, and choir needs practice.',
        lines=[('Sam', 'Long day. Launch moved to Sunday, garden plot sorted, choir needs work. Bed.')],
    ),
]


def _at(hhmm: str, extra_seconds: float = 0.0) -> datetime:
    hours, minutes = (int(x) for x in hhmm.split(':'))
    local = datetime(2026, 3, 14, hours, minutes, tzinfo=timezone.utc)
    return local - timedelta(hours=UTC_OFFSET_H) + timedelta(seconds=extra_seconds)


def _iso(moment: datetime) -> str:
    return utc_iso(moment)


def _hex(seed: str, n: int = 12) -> str:
    return hashlib.sha256(seed.encode('utf-8')).hexdigest()[:n]


def _segments(lines: list[tuple[str, str]], duration_s: float, names: Optional[dict[str, str]] = None) -> list[dict]:
    words = [max(1, len(text.split())) for _, text in lines]
    total = sum(words)
    speech = duration_s * 0.8
    gap = duration_s * 0.2 / (len(lines) + 1)
    out, cursor = [], gap
    speaker_ids: dict[str, str] = {OWNER: 'SPEAKER_00'}
    for (speaker, text), count in zip(lines, words):
        length = speech * count / total
        speaker_id = speaker_ids.setdefault(speaker, f'SPEAKER_{len(speaker_ids):02d}')
        is_user = speaker == OWNER
        label = (names or {}).get(speaker, speaker)
        out.append(
            {
                'start': round(cursor, 2),
                'end': round(cursor + length, 2),
                'speaker': speaker_id,
                'speaker_name': None if label.startswith('Speaker ') else label,
                'is_user': is_user,
                'text': text,
            }
        )
        cursor += length + gap
    return out


def _task(desc: str, due: Optional[str] = None) -> dict:
    return {'key': content_key('task', desc), 'description': desc, 'due_at': due, 'completed': False}


def _memory(content: str, category: str) -> dict:
    return {'key': content_key('memory', content), 'content': content, 'category': category}


def _push(title: str, body: str, trigger: str, at: datetime) -> dict:
    return {'at': _iso(at), 'title': title, 'body': body, 'trigger': trigger}


def _conversation(cid: str, spec: dict, start: datetime, end: datetime, **over: Any) -> dict:
    lines = over.pop('lines', spec['lines'])
    title = over.pop('title', spec.get('title', ''))
    overview = over.pop('overview', spec.get('overview', ''))
    discarded = over.pop('discarded', spec.get('discarded', False))
    tasks = over.pop('tasks', spec.get('tasks', []))
    memories = over.pop('memories', spec.get('memories', []))
    pushes = over.pop('pushes', spec.get('pushes', []))
    names = over.pop('speaker_names', None)
    duration = (end - start).total_seconds()
    push_at = end + timedelta(seconds=40)
    row = {
        'id': cid,
        'baseline_id': over.pop('baseline_id', None),
        'lane': spec.get('lane', 'record'),
        'started_at': _iso(start),
        'finished_at': _iso(end),
        'discarded': discarded,
        'discard_reason': over.pop('discard_reason', spec.get('discard_reason')) if discarded else None,
        'language': 'en',
        'segments': _segments(lines, duration, names),
        'structured': {
            'title': title,
            'overview': overview,
            'emoji': over.pop('emoji', spec.get('emoji', '')),
            'category': spec.get('cat', 'other'),
            'events': [],
        },
        'action_items': [] if discarded else [_task(t) for t in tasks],
        'memories': [] if discarded else [_memory(c, k) for c, k in memories],
        'notifications': [] if discarded else [_push(a, b, c, push_at) for a, b, c in pushes],
        'llm_call_ids': [],
        'evaluable': spec.get('evaluable', {'boundaries': True, 'reason': ''}),
    }
    row.update(over)
    return row


def baseline_conversations() -> list[dict]:
    rows = []
    for i, spec in enumerate(SPECS):
        if spec.get('variant') == 'new':
            continue
        start = _at(spec['t'])
        rows.append(
            _conversation(f'prod-{i:02d}-{_hex(spec["t"], 6)}', spec, start, start + timedelta(minutes=spec['dur']))
        )
    return rows


def _replay_conversations(run_seed: str, mode: str) -> list[dict]:
    """Replay rows for one run. ``mode='main'`` replays the day with two drifted summaries only."""
    baseline = {row['started_at']: row for row in baseline_conversations()}
    out: list[dict] = []
    for i, spec in enumerate(SPECS):
        variant = spec.get('variant', 'same')
        if mode == 'main':
            variant = {'summary': 'summary', 'summary_tasks': 'summary', 'new': 'skip'}.get(variant, 'same')
        start = _at(spec['t'])
        end = start + timedelta(minutes=spec['dur'])
        prod = baseline.get(_iso(start))
        rid = lambda n=0: f'run-{_hex(run_seed + spec["t"] + str(n), 10)}'  # noqa: E731
        bid = prod['id'] if prod else None
        if variant in ('missing', 'skip'):
            continue
        if variant == 'merged_into_prev':
            continue
        if variant == 'new':
            out.append(_conversation(rid(), spec, start, end))
            continue
        if variant == 'same':
            out.append(_conversation(rid(), spec, start, end, baseline_id=bid))
        elif variant in ('summary', 'summary_tasks'):
            over = {'title': spec.get('r_title'), 'overview': spec.get('r_overview')}
            if variant == 'summary_tasks' and mode != 'main':
                over['tasks'] = spec['r_tasks']
            out.append(_conversation(rid(), spec, start, end, baseline_id=bid, **over))
        elif variant == 'tasks':
            out.append(_conversation(rid(), spec, start, end, baseline_id=bid, tasks=spec['r_tasks']))
        elif variant == 'memories':
            out.append(_conversation(rid(), spec, start, end, baseline_id=bid, memories=spec['r_memories']))
        elif variant == 'memories_pushes':
            out.append(
                _conversation(
                    rid(), spec, start, end, baseline_id=bid, memories=spec['r_memories'], pushes=spec['r_pushes']
                )
            )
        elif variant == 'pushes':
            out.append(_conversation(rid(), spec, start, end, baseline_id=bid, pushes=spec['r_pushes']))
        elif variant == 'boundary':
            s2 = start + timedelta(seconds=spec['r_start'])
            e2 = end + timedelta(seconds=spec['r_end'])
            out.append(_conversation(rid(), spec, s2, e2, baseline_id=bid))
        elif variant == 'flip_discard':
            out.append(
                _conversation(
                    rid(), spec, start, end, baseline_id=bid, discarded=True, discard_reason=spec['r_discard_reason']
                )
            )
        elif variant == 'flip_keep':
            out.append(
                _conversation(
                    rid(),
                    spec,
                    start,
                    end,
                    baseline_id=bid,
                    discarded=False,
                    title=spec['r_title'],
                    overview=spec['r_overview'],
                )
            )
        elif variant == 'transcript':
            lines = [(spk, spec['r_lines'].get(n, text)) for n, (spk, text) in enumerate(spec['lines'])]
            out.append(
                _conversation(
                    rid(), spec, start, end, baseline_id=bid, lines=lines, speaker_names=spec['r_speaker_names']
                )
            )
        elif variant == 'split':
            cut = spec['split_at']
            total = len(spec['lines'])
            mid = start + (end - start) * (cut / total)
            for n, (lo, hi, part_lines) in enumerate(
                ((start, mid, spec['lines'][:cut]), (mid + timedelta(seconds=20), end, spec['lines'][cut:]))
            ):
                part = spec['r_split'][n]
                out.append(
                    _conversation(
                        rid(n),
                        spec,
                        lo,
                        hi,
                        baseline_id=bid,
                        lines=part_lines,
                        title=part['title'],
                        overview=part['overview'],
                        tasks=part['tasks'],
                        emoji=part.get('emoji', spec['emoji']),
                    )
                )
        elif variant == 'merge':
            nxt = SPECS[i + 1]
            n_start = _at(nxt['t'])
            n_end = n_start + timedelta(minutes=nxt['dur'])
            nxt_prod = baseline.get(_iso(n_start))
            row = _conversation(
                rid(),
                spec,
                start,
                n_end,
                baseline_id=bid,
                lines=spec['lines'] + nxt['lines'],
                title=nxt['r_merge_title'],
                overview=nxt['r_merge_overview'],
                tasks=spec['tasks'] + nxt['tasks'],
            )
            row['baseline_ids'] = [bid, nxt_prod['id']] if nxt_prod else [bid]
            out.append(row)
        else:
            raise ValueError(f'unknown variant {variant}')
    out.sort(key=lambda r: r['started_at'])
    return out


# ---- LLM calls and day-level outputs --------------------------------------------------------

NOTES_SYSTEM = (
    'You turn a conversation transcript into a title, an overview, an emoji, a category, action items and events. '
    'Write the overview in the third person. Return JSON.'
)


def _llm_calls(run_seed: str, conversations: list[dict], changed_ids: set[str]) -> list[dict]:
    calls = []
    for conv in conversations:
        if conv['discarded']:
            stages = [('discard', 'discard_check', 'gpt-4.1-nano')]
        else:
            stages = [
                ('discard', 'discard_check', 'gpt-4.1-nano'),
                ('notes', 'conversation_notes', 'gpt-4.1-mini'),
                ('memories', 'memory_extraction', 'gpt-4.1-mini'),
            ]
            if conv['action_items']:
                stages.append(('tasks', 'action_item_dedup', 'gpt-4.1-nano'))
        ids = []
        for n, (stage, feature, model) in enumerate(stages):
            cid = f'call-{_hex(run_seed + conv["id"] + stage, 12)}'
            transcript = '\n'.join(f"{s.get('speaker_name') or 'Unknown'}: {s['text']}" for s in conv['segments'])
            if stage == 'notes':
                output = json.dumps(
                    {
                        'title': conv['structured']['title'],
                        'overview': conv['structured']['overview'],
                        'emoji': conv['structured']['emoji'],
                        'category': conv['structured']['category'],
                        'action_items': [t['description'] for t in conv['action_items']],
                        'events': [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                prompt = [{'role': 'system', 'content': NOTES_SYSTEM}, {'role': 'user', 'content': transcript}]
            elif stage == 'memories':
                output = json.dumps([m['content'] for m in conv['memories']], ensure_ascii=False, indent=2)
                prompt = [
                    {
                        'role': 'system',
                        'content': 'Extract durable facts about the user worth remembering. Return a JSON list.',
                    },
                    {'role': 'user', 'content': transcript},
                ]
            elif stage == 'tasks':
                output = json.dumps({'duplicates': []})
                prompt = [
                    {
                        'role': 'system',
                        'content': 'Given new action items and open ones from the last 7 days, list duplicates.',
                    },
                    {'role': 'user', 'content': json.dumps([t['description'] for t in conv['action_items']])},
                ]
            else:
                output = json.dumps({'discard': conv['discarded'], 'reason': conv.get('discard_reason')})
                prompt = [
                    {'role': 'system', 'content': 'Decide whether this transcript is worth keeping as a conversation.'},
                    {'role': 'user', 'content': transcript},
                ]
            tokens_in = 120 + 3 * len(transcript.split()) + 40 * n
            tokens_out = 20 + len(output) // 4
            hit = conv['id'] not in changed_ids or stage == 'discard'
            rate_in, rate_out = (0.4e-6, 1.6e-6) if 'mini' in model else (0.1e-6, 0.4e-6)
            calls.append(
                {
                    'id': cid,
                    'at': conv['finished_at'],
                    'stage': stage,
                    'conversation_id': conv['id'],
                    'feature': feature,
                    'model': model,
                    'prompt': prompt,
                    'output': output,
                    'tokens_in': tokens_in,
                    'tokens_out': tokens_out,
                    'usd': 0.0 if hit else round(tokens_in * rate_in + tokens_out * rate_out, 6),
                    'cache_hit': bool(hit),
                    'ms': 3.0 if hit else float(400 + 37 * len(output) % 1900),
                }
            )
            ids.append(cid)
        conv['llm_call_ids'] = ids
    return calls


def _daily_summaries() -> tuple[dict, dict]:
    production = {
        'title': 'Launch moved, garden sorted',
        'overview': 'A busy Saturday in Lumen Bay: the rocket launch moved to Sunday, Sam took the sunny garden plot, and the choir needs another rehearsal.',
        'highlights': [
            'Zephyr launch moved to Sunday 9:00',
            'Corner plot at the community garden',
            "Dad's 70th birthday picnic planned for the 28th",
        ],
    }
    replay = {
        'title': 'Launch moved, garden plot and a birthday plan',
        'overview': "A busy Saturday in Lumen Bay: the rocket launch moved to Sunday at nine, Sam took the sunny corner plot with Basil, and Sam and Wren planned Dad's 70th on Gull Island.",
        'highlights': [
            'Zephyr launch moved to Sunday 9:00',
            'Sunny corner plot shared with Basil',
            "Dad's 70th: Gull Island picnic on the 28th",
            'Learn the alto line by Thursday',
        ],
    }
    return production, replay


def _run_record(run_id: str, ref: str, commit: str, conversations: list[dict], calls: list[dict], **over: Any) -> dict:
    started = _at('23:59') + timedelta(days=3, hours=2)
    spend = round(sum(c['usd'] for c in calls), 4)
    hits = sum(1 for c in calls if c['cache_hit'])
    stage_names = (
        'ingest',
        'transcribe',
        'boundaries',
        'speakers',
        'discard',
        'notes',
        'memories',
        'tasks',
        'notifications',
        'goals',
        'daily_summary',
        'chat_index',
    )
    timings = dict(zip(stage_names, (4.1, 38.0, 6.2, 11.5, 22.4, 141.7, 96.3, 54.0, 3.1, 18.8, 12.4, 9.6)))
    stages = {}
    for name in stage_names:
        stage_calls = [c for c in calls if c['stage'] == name]
        stages[name] = {
            'status': 'complete' if stage_calls or name in ('ingest', 'boundaries', 'notifications') else 'cached',
            'cache_hits': sum(1 for c in stage_calls if c['cache_hit']),
            'cache_misses': sum(1 for c in stage_calls if not c['cache_hit']),
        }
    record = {
        'run_id': run_id,
        'day_id': DAY_ID,
        'ref': ref,
        'commit': commit,
        'backend_tree': _hex(ref + 'tree', 40),
        'overlay': {
            'env': {'NOTES_PROMPT_VERSION': 'v7', 'MEMORY_DEDUP_THRESHOLD': '0.82'},
            'models': {'notes': 'gpt-4.1-mini'},
            'serving_for': {'notes_identity': 'on', 'record_lane': 'batch_live_v1'},
        },
        'start_state': 'approximate',
        'status': 'complete',
        'started_at': _iso(started),
        'finished_at': _iso(started + timedelta(seconds=sum(timings.values()))),
        'spend_usd': spend,
        'budget_usd': 5.0,
        'timings': timings,
        'stages': stages,
        'warnings': [
            'start state approximate: snapshot taken after the replayed day',
            f'{hits} of {len(calls)} LLM calls served from cache',
        ],
    }
    record.update(over)
    return record


# ---- audio ------------------------------------------------------------------------------


def _tone_block(freq: float, rate: int) -> bytes:
    """One second of an 8-bit tone with a 4 Hz syllable envelope: soft enough to listen to for a while."""
    out = bytearray(rate)
    for n in range(rate):
        t = n / rate
        envelope = 0.55 + 0.45 * math.sin(2 * math.pi * 4 * t)
        out[n] = int(128 + 34 * envelope * math.sin(2 * math.pi * freq * t)) & 0xFF
    return bytes(out)


def write_wav(path: Path, duration_s: float, segments: list[tuple[float, float, float]], rate: int) -> None:
    """8-bit mono PCM WAV of ``duration_s``; each (start, end, freq) segment is a tone, the rest silence."""
    total = max(1, int(duration_s * rate))
    pcm = bytearray(b'\x80' * total)
    blocks: dict[float, bytes] = {}
    for start, end, freq in segments:
        a, b = max(0, int(start * rate)), min(total, int(end * rate))
        if b <= a:
            continue
        block = blocks.setdefault(freq, _tone_block(freq, rate))
        need = b - a
        pcm[a:b] = (block * (need // rate + 1))[:need]
    header = b'RIFF' + struct.pack('<I', 36 + total) + b'WAVE'
    header += b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate, 1, 8)
    header += b'data' + struct.pack('<I', total)
    _write_bytes(path, header + bytes(pcm))


# ---- writing -----------------------------------------------------------------------------


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _write_bytes(path: Path, body: bytes) -> None:
    _private_dir(path.parent)
    tmp = path.with_name(f'.{path.name}.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(body)
    os.replace(tmp, path)


def _write_json(path: Path, value: Any) -> None:
    _write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))


def _write_jsonl(path: Path, rows: list[Any]) -> None:
    body = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows)
    _write_bytes(path, body.encode('utf-8'))


def _inside_git(path: Path) -> bool:
    return any((p / '.git').exists() for p in (path, *path.parents))


def write_sample(root: Path, verdicts_root: Optional[Path] = None, *, audio_rate: int = 8000) -> dict[str, Any]:
    """Write the sample day and both runs under ``root``; sample verdicts only when ``verdicts_root`` is given."""
    root = Path(root).expanduser().resolve()
    if _inside_git(root):
        raise SystemExit('refusing to write lab data inside a git worktree')
    _private_dir(root)
    for name in ('corpus', 'cache', 'runs'):
        _private_dir(root / name)
    day_dir = root / 'corpus' / DAY_ID
    baseline = baseline_conversations()

    # audio: one clip per production conversation, plus the capture production lost (the replay's "new" one)
    index = []
    lead = 15.0
    clips: list[tuple[str, dict]] = [(row['id'], row) for row in baseline]
    for i, spec in enumerate(SPECS):
        if spec.get('variant') == 'new':
            start = _at(spec['t'])
            capture = _conversation(
                f'capture-{_hex(spec["t"], 8)}', spec, start, start + timedelta(minutes=spec['dur'])
            )
            clips.append((capture['id'], capture))
    total_audio = 0.0
    for clip_id, row in clips:
        start = datetime.fromisoformat(row['started_at'].replace('Z', '+00:00')) - timedelta(seconds=lead)
        end = datetime.fromisoformat(row['finished_at'].replace('Z', '+00:00')) + timedelta(seconds=lead)
        tones = [
            (lead + s['start'], lead + s['end'], SPEAKER_TONES.get(_speaker_of(row, s), DEFAULT_TONE))
            for s in row['segments']
        ]
        duration = (end - start).total_seconds()
        total_audio += duration
        write_wav(day_dir / 'audio' / f'{clip_id}.wav', duration, tones, audio_rate)
        index.append(
            {
                'conversation_id': clip_id,
                'path': f'{clip_id}.wav',
                'start': _iso(start),
                'end': _iso(end),
                'codec': 'pcm_u8',
                'sample_rate': audio_rate,
            }
        )
    _write_json(day_dir / 'audio' / 'index.json', index)

    lanes: dict[str, int] = {}
    for row in baseline:
        lanes[row['lane']] = lanes.get(row['lane'], 0) + 1
    _write_json(
        day_dir / 'day.json',
        {
            'day_id': DAY_ID,
            'date': DATE,
            'timezone': TIMEZONE,
            'source_snapshot': 'synthetic-sample',
            'start_state_snapshot': 'synthetic-sample',
            'coverage': {
                'audio_seconds': round(total_audio, 1),
                'conversations': len(baseline),
                'with_audio': len(baseline),
                'lanes': lanes,
                'gaps': [{'start': _iso(_at(a)), 'end': _iso(_at(b)), 'kind': 'unknown'} for a, b in GAPS],
            },
        },
    )

    production_summary, replay_summary = _daily_summaries()
    base_dir = day_dir / 'baseline'
    _write_jsonl(base_dir / 'conversations.jsonl', baseline)
    _write_jsonl(
        base_dir / 'memories.jsonl', [dict(m, conversation_id=c['id']) for c in baseline for m in c['memories']]
    )
    _write_jsonl(
        base_dir / 'action_items.jsonl',
        [dict(t, conversation_id=c['id']) for c in baseline for t in c['action_items']],
    )
    production_pushes = [dict(n, conversation_id=c['id']) for c in baseline for n in c['notifications']]
    production_pushes.append(_push('Your day in Lumen Bay', production_summary['title'], 'daily_summary', _at('22:00')))
    _write_jsonl(base_dir / 'notifications.jsonl', production_pushes)
    _write_json(base_dir / 'daily_summary.json', production_summary)

    runs = []
    for run_id, ref, commit, mode in (
        (RUN_ID, 'feat/summary-prompt-v7', _hex('v7', 40), 'variant'),
        (MAIN_RUN_ID, 'main', _hex('main', 40), 'main'),
    ):
        conversations = _replay_conversations(run_id, mode)
        twins = {b['id']: b for b in baseline}
        changed = {c['id'] for c in conversations if not c['baseline_id'] or _differs(c, twins.get(c['baseline_id']))}
        calls = _llm_calls(run_id, conversations, changed)
        run_dir = root / 'runs' / run_id
        for conv in conversations:
            _write_json(run_dir / 'conversations' / f'{conv["id"]}.json', conv)
        _write_jsonl(run_dir / 'llm_calls.jsonl', calls)
        pushes = [dict(n, conversation_id=c['id']) for c in conversations for n in c['notifications']]
        summary = replay_summary if mode == 'variant' else production_summary
        pushes.append(_push('Your day in Lumen Bay', summary['title'], 'daily_summary', _at('22:00')))
        _write_json(
            run_dir / 'day.json',
            {
                'daily_summary': summary,
                'goals': [
                    {'title': 'Practice choir parts 3x a week', 'progress_before': 1, 'progress_after': 2, 'target': 3},
                    {
                        'title': 'Launch the Zephyr rocket this spring',
                        'progress_before': 0.4,
                        'progress_after': 0.55 if mode == 'variant' else 0.5,
                        'target': 1,
                        'note': 'launch date set',
                    },
                ],
                'memory_delta': {
                    'added': [m for c in conversations for m in c['memories']],
                    'updated': (
                        [
                            {
                                'before': _memory('Sam has a plot at the Lumen Bay community garden', 'personal'),
                                'after': _memory(
                                    'Sam has the sunny corner plot at the Lumen Bay community garden', 'personal'
                                ),
                            }
                        ]
                        if mode == 'variant'
                        else []
                    ),
                    'removed': (
                        [_memory('Sam is learning the tenor line in choir', 'hobby')] if mode == 'variant' else []
                    ),
                },
                'notifications': pushes,
            },
        )
        _write_jsonl(
            run_dir / 'vendor_log.jsonl',
            [
                {
                    'at': _iso(_at('23:59') + timedelta(days=3)),
                    'vendor': 'cassette',
                    'purpose': 'stt playback',
                    'audio_seconds': round(total_audio, 1),
                    'usd': 0.0,
                    'destination': 'local cassette',
                }
            ],
        )
        _write_jsonl(
            run_dir / 'decisions.jsonl',
            [
                {
                    'at': _iso(_at('23:59') + timedelta(days=3)),
                    'name': 'notes_identity',
                    'mode': 'on',
                    'source': 'overlay',
                },
                {
                    'at': _iso(_at('23:59') + timedelta(days=3)),
                    'name': 'record_lane',
                    'mode': 'batch_live_v1',
                    'source': 'overlay',
                },
            ],
        )
        record = _run_record(run_id, ref, commit, conversations, calls)
        if mode == 'main':
            record['overlay'] = {}
            record['warnings'] = record['warnings'][:1]
        _write_json(run_dir / 'run.json', record)
        runs.append({'run_id': run_id, 'conversations': len(conversations), 'llm_calls': len(calls)})

    verdict_count = 0
    if verdicts_root is not None:
        verdict_count = _write_sample_verdicts(Path(verdicts_root).expanduser(), root)
    return {
        'root': str(root),
        'day_id': DAY_ID,
        'runs': runs,
        'baseline_conversations': len(baseline),
        'audio_clips': len(index),
        'verdicts': verdict_count,
    }


def _speaker_of(row: dict, segment: dict) -> str:
    if segment.get('is_user'):
        return OWNER
    return segment.get('speaker_name') or segment.get('speaker') or ''


def _differs(conv: dict, twin: Optional[dict]) -> bool:
    if twin is None:
        return True
    strip = lambda c: {k: v for k, v in c.items() if k not in ('id', 'baseline_id', 'llm_call_ids')}  # noqa: E731
    return json.dumps(strip(conv), sort_keys=True) != json.dumps(strip(twin), sort_keys=True)


def _write_sample_verdicts(verdicts_root: Path, root: Path) -> int:
    run_dir = root / 'runs' / RUN_ID
    convs = sorted(
        (json.loads(p.read_text()) for p in (run_dir / 'conversations').glob('*.json')), key=lambda c: c['started_at']
    )
    run = json.loads((run_dir / 'run.json').read_text())
    reader = Reader(root, verdicts_root)
    picks = []
    for conv in convs:
        title = conv['structured']['title']
        if title.startswith('Lighthouse co-op'):
            picks.append((conv, 'summary', summary_key(conv['structured']), 'good', 'Clearer than production.'))
        if conv['action_items'] and title.startswith('Sunday fish stew'):
            item = conv['action_items'][0]
            picks.append((conv, 'task', item['key'], 'bad', 'Lost "saffron is for the stew" context.'))
        if conv['notifications'] and title.startswith('Reminder to water'):
            n = conv['notifications'][1]
            picks.append((conv, 'notification', notification_key(n), 'bad', 'Unprompted proactive push.'))
        if title.startswith('Rocket club'):
            picks.append((conv, 'boundary', boundary_key(conv), 'good', ''))
    rows = []
    for n, (conv, kind, key, mark, note) in enumerate(picks):
        rows.append(
            {
                'id': new_verdict_id(),
                'at': _iso(_at('23:59') + timedelta(days=3, hours=3, minutes=n)),
                'run_id': RUN_ID,
                'day_id': DAY_ID,
                'ref': run['ref'],
                'conversation_id': conv['id'],
                'item_kind': kind,
                'item_key': key,
                'mark': mark,
                'note': note,
                'item_snapshot': views.locate_item(reader, run, conv['id'], kind, key),
            }
        )
    _private_dir(verdicts_root)
    _write_jsonl(verdicts_root / 'verdicts.jsonl', rows)
    return len(rows)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', required=True, help='store root to write (outside any git worktree)')
    parser.add_argument('--verdicts', help='also write a few sample verdicts to this verdict root')
    parser.add_argument('--audio-rate', type=int, default=8000, help='WAV sample rate (Hz)')
    args = parser.parse_args(argv)
    result = write_sample(Path(args.root), Path(args.verdicts) if args.verdicts else None, audio_rate=args.audio_rate)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
