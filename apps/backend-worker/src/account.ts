import { DurableObject } from "cloudflare:workers";

import {
  gatewayConfig,
  gatewayModeEnabled,
  generateViaGateway,
  type GatewaySecretEnv,
} from "./openrouter";
import { gatewayFailureEvent } from "./observability";
import {
  admitMessage,
  cancelGeneration,
  completeGeneration,
  countPendingGenerations,
  failGeneration,
  hasGeneration,
  readGenerationEvents,
  readPendingGeneration,
  terminalEvent,
  type Admission,
} from "./chat";
import type { ChatCreate, GenerationEvent } from "./wire";

export class AccountBackend extends DurableObject<Env & GatewaySecretEnv> {
  private readonly waiters = new Map<
    string,
    Set<(event: GenerationEvent) => void>
  >();

  async admit(
    accountId: string,
    input: ChatCreate,
    chatLimit: number | null
  ): Promise<Admission | "conflict" | "entitlement" | "attachment_rejected"> {
    const result = await admitMessage(this.env.DB, accountId, input, chatLimit);
    if (result !== "conflict" && result !== "entitlement") {
      await this.ensureGenerationAlarm(accountId);
    }
    return result;
  }

  async cancel(
    accountId: string,
    generationId: string
  ): Promise<"not_found" | "accepted" | "terminal"> {
    const result = await cancelGeneration(this.env.DB, accountId, generationId);
    if (result === "not_found" || result === "terminal") return result;
    this.notifyWaiters(generationId, result);
    return "accepted";
  }

  override async alarm(): Promise<void> {
    const accountId = this.accountId;
    const pending = await readPendingGeneration(this.env.DB, accountId);
    if (pending === null) return;
    await this.runGeneration(
      accountId,
      pending.generationId,
      pending.input.text
    );
    await this.ensureGenerationAlarm(accountId);
  }

  override async fetch(request: Request): Promise<Response> {
    const accountId = this.accountId;
    const generationId = new URL(request.url).searchParams.get("generationId");
    if (
      generationId === null ||
      !(await hasGeneration(this.env.DB, accountId, generationId))
    )
      return new Response(null, { status: 404 });
    const lastEventId = request.headers.get("last-event-id");
    const allEvents = await readGenerationEvents(
      this.env.DB,
      accountId,
      generationId
    );
    const replay = this.selectReplay(allEvents, lastEventId);
    if (replay === "expired")
      return Response.json(
        {
          error: {
            code: "generation_replay_expired",
            retryable: false,
            action: "refresh_history",
          },
        },
        { status: 410, headers: { "cache-control": "no-store" } }
      );
    const existing = replay;
    if (existing.some((event) => this.isTerminal(event)))
      return this.sse(existing);
    const encoder = new TextEncoder();
    let listener: ((event: GenerationEvent) => void) | undefined;
    const stream = new ReadableStream<Uint8Array>({
      start: (controller) => {
        for (const event of existing)
          controller.enqueue(encoder.encode(this.encode(event)));
        listener = (event) => {
          try {
            controller.enqueue(encoder.encode(this.encode(event)));
            if (this.isTerminal(event)) controller.close();
          } catch {
            this.waiters.get(generationId)?.delete(listener!);
          }
        };
        const listeners = this.waiters.get(generationId) ?? new Set();
        listeners.add(listener);
        this.waiters.set(generationId, listeners);
      },
      cancel: () => {
        if (listener !== undefined)
          this.waiters.get(generationId)?.delete(listener);
      },
    });
    return new Response(stream, {
      headers: {
        "cache-control": "no-cache, no-store",
        "content-type": "text/event-stream",
      },
    });
  }

  private get accountId(): string {
    const name = this.ctx.id.name;
    if (name === null || name === undefined)
      throw new Error("account DO must be named");
    return name;
  }

  private async ensureGenerationAlarm(accountId: string): Promise<void> {
    const pending = await countPendingGenerations(this.env.DB, accountId);
    if (pending > 0 && (await this.ctx.storage.getAlarm()) === null) {
      await this.ctx.storage.setAlarm(Date.now() + 1_000);
    }
  }

  private async runGeneration(
    accountId: string,
    generationId: string,
    prompt: string
  ): Promise<void> {
    const terminal = await terminalEvent(this.env.DB, accountId, generationId);
    if (terminal !== null) return;

    if (gatewayModeEnabled(this.env)) {
      const config = gatewayConfig(this.env);
      if (config === null) {
        console.error(
          JSON.stringify(
            gatewayFailureEvent({
              message: "gateway_unconfigured",
              correlationId: generationId,
              model: "unconfigured",
              status: 0,
            })
          )
        );
        const event = await failGeneration(
          this.env.DB,
          accountId,
          generationId
        );
        this.notifyWaiters(generationId, event);
        return;
      }
      const result = await generateViaGateway(config, prompt, generationId);
      if (result.kind === "error") {
        const event = await failGeneration(
          this.env.DB,
          accountId,
          generationId
        );
        this.notifyWaiters(generationId, event);
      } else {
        const event = await completeGeneration(
          this.env.DB,
          accountId,
          generationId,
          result.text
        );
        this.notifyWaiters(generationId, event);
      }
      return;
    }

    try {
      const result = await this.env.AI.run(
        this.env.AI_MODEL as keyof AiModels,
        {
          messages: [
            {
              role: "system",
              content: "You are Omi, a concise and helpful personal assistant.",
            },
            { role: "user", content: prompt },
          ],
          max_tokens: 768,
        }
      );
      const response = result as { response?: unknown };
      if (
        typeof response.response !== "string" ||
        response.response.length === 0
      ) {
        const event = await failGeneration(
          this.env.DB,
          accountId,
          generationId
        );
        this.notifyWaiters(generationId, event);
      } else {
        const event = await completeGeneration(
          this.env.DB,
          accountId,
          generationId,
          response.response
        );
        this.notifyWaiters(generationId, event);
      }
    } catch {
      const event = await failGeneration(this.env.DB, accountId, generationId);
      this.notifyWaiters(generationId, event);
    }
  }

  private notifyWaiters(generationId: string, event: GenerationEvent): void {
    for (const listener of this.waiters.get(generationId) ?? [])
      listener(event);
    if (this.isTerminal(event)) this.waiters.delete(generationId);
  }

  encode(event: GenerationEvent): string {
    const { id: _id, ...frame } = event;
    return `id: ${event.id}\nevent: ${event.kind}\ndata: ${JSON.stringify(
      frame
    )}\n\n`;
  }

  private sse(events: GenerationEvent[]): Response {
    return new Response(events.map((event) => this.encode(event)).join(""), {
      headers: {
        "cache-control": "no-cache, no-store",
        "content-type": "text/event-stream",
      },
    });
  }

  isTerminal(event: GenerationEvent): boolean {
    return (
      event.kind === "done" ||
      event.kind === "failed" ||
      event.kind === "cancelled"
    );
  }

  selectReplay(
    events: GenerationEvent[],
    lastEventId: string | null
  ): GenerationEvent[] | "expired" {
    if (lastEventId === null) return events;
    const terminal = events.find((event) => this.isTerminal(event));
    const cursorIndex = events.findIndex((event) => event.id === lastEventId);
    if (cursorIndex < 0) return terminal === undefined ? "expired" : [terminal];
    const replay = events.slice(cursorIndex + 1);
    return replay.length === 0 && terminal !== undefined ? [terminal] : replay;
  }
}
