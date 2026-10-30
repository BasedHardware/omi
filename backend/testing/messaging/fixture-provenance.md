These fixtures are synthetic, sanitized recordings of the *documented* provider
payload shapes, captured 2026-10-10 from the official references below. They are
not recordings of a customer or live sandbox delivery. Numbers use the reserved
202-555-01xx range; IDs, names, credentials and content are invented.

- https://core.telegram.org/bots/api#update
- https://docs.linqapp.com/channel/imessage/guides/webhooks/events/
- https://docs.linqapp.com/channel/imessage/guides/webhooks/
- https://docs.linqapp.com/channel/imessage/guides/messaging/sending-messages/

`responses.json` replays documented Telegram retry_after and Linq Retry-After,
plus synthetic 503 failures. Live discoveries must be sanitized and added to this
suite before being claimed as verified live fixes. Fixtures are authored test
input, never harvested message data or a training/evaluation corpus.
