"""At-most-once, fleet-bounded language qualification intents; no serving job writes."""

from datetime import datetime, timedelta, timezone
import hashlib
import math
import time

from config.batch_pipeline_shadow import language_only_enabled, language_probe_limit, shadow_percent


class LanguageShadowStore:
    def __init__(self, store, *, clock=time.time):
        self.store, self.clock = store, clock

    def reserve(self, item):
        now, limit = self.clock(), language_probe_limit()
        if not language_only_enabled() or not shadow_percent() or not limit:
            return False
        key = hashlib.sha256(f'{item.owner_id}\0{item.segment_id}'.encode()).hexdigest()
        hour, minute = str(int(now // 3600)), 'm' + str(int(now // 60))

        def claim(tx):
            prior = tx.get('shadow_lid_probes', key)
            budget = tx.get('shadow_lid_spend', hour)
            burst = tx.get('shadow_lid_spend', minute)
            active = tx.get('shadow_lid_spend', 'active').get('slots', [])
            if len(active) > 2:
                return False
            slots = [*active, *({} for _ in range(2 - len(active)))]
            # Expiry revokes permission; only completion releases occupancy.
            # A hung/crashed owner creates an explicit HOLD, never overlapping IO.
            slot = next((i for i, value in enumerate(slots) if not value), None)
            if (
                prior
                or slot is None
                or budget.get('units', 0) >= limit
                or burst.get('units', 0) >= math.ceil(limit / 60)
                or not language_only_enabled()
                or not shadow_percent()
            ):
                return False
            tx.check_privacy(
                item.owner_id,
                (item.conversation_id,) if item.conversation_id else (),
                item.privacy_generation,
            )
            expiry = datetime.fromtimestamp(now, timezone.utc) + timedelta(days=7)
            # No raw owner, conversation, input/output or language evidence is persisted.
            # A lost commit reply consumes the attempt; retries cannot repeat a probe.
            tx.put('shadow_lid_probes', key, {'reserved_at': now, 'expires_at': expiry})
            slots[slot] = {'key': key, 'until': now + 120}
            tx.put('shadow_lid_spend', 'active', {'slots': slots, 'expires_at': expiry})
            for bucket, state in ((hour, budget), (minute, burst)):
                tx.put('shadow_lid_spend', bucket, {'units': state.get('units', 0) + 1, 'expires_at': expiry})
            return True

        try:
            return self.store.run(claim)
        except Exception:
            return False

    def authorize(self, item):
        if not language_only_enabled() or not shadow_percent():
            return False
        key = hashlib.sha256(f'{item.owner_id}\0{item.segment_id}'.encode()).hexdigest()

        def check(tx):
            slots = tx.get('shadow_lid_spend', 'active').get('slots', [])
            if not any(s.get('key') == key and s.get('until', 0) > self.clock() for s in slots):
                return False
            tx.check_privacy(
                item.owner_id,
                (item.conversation_id,) if item.conversation_id else (),
                item.privacy_generation,
            )
            return True

        return self.store.run(check)

    def release(self, item):
        key = hashlib.sha256(f'{item.owner_id}\0{item.segment_id}'.encode()).hexdigest()

        def finish(tx):
            active = tx.get('shadow_lid_spend', 'active')
            slots = active.get('slots', [])
            if any(s.get('key') == key for s in slots):
                tx.put(
                    'shadow_lid_spend',
                    'active',
                    {
                        **active,
                        'slots': [{} if s.get('key') == key else s for s in slots],
                    },
                )

        self.store.run(finish)
