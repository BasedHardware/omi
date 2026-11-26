# Server recovery waits for usable batch audio

When pusher cannot commit its tail, a server-batch capture can retain audio
references without committed bounds or preview content. Self-heal and the
outbox admission transaction now refuse this shape. The capture stays available
to its producer. A later durable span or preview lets recovery admit it. A
close marker alone cannot make these audio references safe to delete.

Quiet checks still respect the producer lease and close a drained archive
after its grace period. An expired quiet check without close proof retires
without editing the capture. The bounded self-heal sweep can pick up a later
commit. If an already-admitted job hits the open archive exception, the worker
logs `server_batch_archive_not_closed` and uses its existing failure budget.

[Server batch-only capture and durable quiet checks](../../listen_pusher_pipeline.mdx#server-batch-only-capture-by-platform)
