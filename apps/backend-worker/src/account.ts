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
import {
  composeGenerationPrompt,
  isVisibleGenerationText,
} from "./generation-prompt";
import { openLiveGenerationSse } from "./generation-sse";
import type { ChatCreate, ChatMessage, GenerationEvent } from "./wire";

function projectExternalGenerationFrame(event: GenerationEvent): unknown {
  if (event.kind !== "done" && event.kind !== "cancelled") {
    const { id: _id, ...frame } = event;
    return frame;
  }
  if (event.kind === "cancelled" && event.message === null) {
    return { kind: "cancelled", message: null };
  }
  const message = event.message as ChatMessage | null | undefined;
  if (message === null || message === undefined || message.sender !== "ai") {
    throw new TypeError(
      "terminal Chat frame has no canonical assistant message"
    );
  }
  return {
    kind: event.kind,
    message: {
      ...message,
      generationOutcome: event.kind === "done" ? "completed" : "cancelled",
    },
  };
}

export class AccountBackend extends DurableObject<Env & GatewaySecretEnv> {
  private readonly waiters = new Map<
    string,
    Set<(event: GenerationEvent) => void>
  >();

  async admit(
    accountId: string,
    input: ChatCreate,
    chatLimit: number | null
  ): Promise<
    | Admission
    | "conflict"
    | "entitlement"
    | "attachment_rejected"
    | "attachment_not_found"
    | "attachment_invalid"
  > {
    return this.ctx.blockConcurrencyWhile(async () => {
      const result = await admitMessage(
        this.env.DB,
        accountId,
        input,
        chatLimit
      );
      if (typeof result !== "string") {
        await this.ensureGenerationAlarm(accountId);
      }
      return result;
    });
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
    if (pending.input === "unreadable") {
      const event = await failGeneration(
        this.env.DB,
        accountId,
        pending.generationId
      );
      this.notifyWaiters(pending.generationId, event);
      await this.ensureGenerationAlarm(accountId);
      return;
    }
    await this.runGeneration(accountId, pending.generationId, pending.input);
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
    if (lastEventId === "")
      return Response.json(
        {
          error: {
            code: "bad_request",
            retryable: false,
            action: "edit_request",
          },
        },
        { status: 400, headers: { "cache-control": "no-store" } }
      );
    const allEvents = await readGenerationEvents(
      this.env.DB,
      accountId,
      generationId
    );
    if (allEvents === "unreadable")
      return Response.json(
        {
          error: {
            code: "service_unavailable",
            retryable: true,
            action: "retry",
          },
        },
        {
          status: 503,
          headers: { "cache-control": "no-store", "retry-after": "60" },
        }
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
    const stream = openLiveGenerationSse(
      (event) => this.encode(event),
      existing,
      (listener) => {
        const listeners = this.waiters.get(generationId) ?? new Set();
        listeners.add(listener);
        this.waiters.set(generationId, listeners);
        return () => {
          this.waiters.get(generationId)?.delete(listener);
        };
      },
      (event) => this.isTerminal(event)
    );
    return new Response(stream, {
      headers: {
        "cache-control": "no-store",
        "content-type": "text/event-stream",
        "x-accel-buffering": "no",
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
    input: ChatCreate
  ): Promise<void> {
    const terminal = await terminalEvent(this.env.DB, accountId, generationId);
    if (terminal === "unreadable") {
      const event = await failGeneration(this.env.DB, accountId, generationId);
      this.notifyWaiters(generationId, event);
      return;
    }
    if (terminal !== null) return;

    const composed = await composeGenerationPrompt(
      this.env.DB,
      this.env.ATTACHMENTS,
      accountId,
      input.id,
      input.text
    );
    if (composed.kind === "unavailable") {
      const event = await failGeneration(
        this.env.DB,
        accountId,
        generationId,
        false
      );
      this.notifyWaiters(generationId, event);
      return;
    }
    if (composed.kind === "fail") {
      const event = await failGeneration(this.env.DB, accountId, generationId);
      this.notifyWaiters(generationId, event);
      return;
    }
    const prompt = composed.prompt;

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
      const result = await generateViaGateway(
        config,
        prompt,
        generationId,
        composed.history
      );
      if (result.kind === "error" || !isVisibleGenerationText(result.text)) {
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
            ...composed.history,
            { role: "user", content: prompt },
          ],
          max_tokens: 768,
        }
      );
      const response = result as { response?: unknown };
      if (!isVisibleGenerationText(response.response)) {
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
    } catch (error) {
      if (
        error instanceof TypeError &&
        error.message === "invalid chat message record"
      ) {
        throw error;
      }
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
    return `event: ${event.kind}\nid: ${event.id}\ndata: ${JSON.stringify(
      projectExternalGenerationFrame(event)
    )}\n\n`;
  }

  private sse(events: GenerationEvent[]): Response {
    return new Response(events.map((event) => this.encode(event)).join(""), {
      headers: {
        "cache-control": "no-store",
        "content-type": "text/event-stream",
        "x-accel-buffering": "no",
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
