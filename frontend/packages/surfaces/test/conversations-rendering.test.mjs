import assert from "node:assert/strict";
import test, { after } from "node:test";

import { EN_MESSAGES } from "@omi-core/i18n";
import {
  closeRenderHarness,
  loadProductionExport,
  renderComponent,
} from "./render-harness.mjs";

after(closeRenderHarness);

async function renderConversation(state, detail = false, initialFolderId) {
  const ConversationsProduction = await loadProductionExport("ConversationsProduction.tsx", "ConversationsProduction");
  const fixtureConversationStore = await loadProductionExport("conversation-fixtures.ts", "fixtureConversationStore");
  const fixtureFolderStore = await loadProductionExport("conversation-fixtures.ts", "fixtureFolderStore");
  const fixtureConversationDetailId = await loadProductionExport("conversation-fixtures.ts", "fixtureConversationDetailId");
  return renderComponent(ConversationsProduction, {
    store: fixtureConversationStore(state, detail),
    foldersStore: fixtureFolderStore(),
    fixture: state,
    ...(detail ? { detailId: fixtureConversationDetailId(state) } : {}),
    ...(initialFolderId ? { initialFolderId } : {}),
  });
}

test("a folder route opens Conversations with that folder selected", async () => {
  const rendered = await renderConversation("normal", false, "work-folder-one");
  try {
    await rendered.act(async () => {
      for (let index = 0; index < 6; index += 1) await Promise.resolve();
    });
    const selected = [...rendered.container.querySelectorAll(".conversation-filter button")]
      .find((button) => button.textContent?.trim() === "Work");
    assert.equal(selected?.getAttribute("aria-pressed"), "true");
    assert.match(
      rendered.container.querySelector('main[data-route="conversations"]')?.getAttribute("data-consumer-semantic") ?? "",
      /conversations:visible:3:total:7:/,
      "the selected folder controls the visible conversation projection",
    );
  } finally {
    await rendered.cleanup();
  }
});

test("conversation rows render the compact accessible reference shape", async () => {
  const rendered = await renderConversation("normal");
  try {
    const row = rendered.container.querySelector(".conversation-row");
    assert.ok(row, "normal fixture renders a conversation row");
    assert.equal(row.querySelector(".conversation-avatar")?.getAttribute("aria-hidden"), "true");
    const star = row.querySelector("button.conversation-star");
    assert.ok(star, "row renders a star affordance");
    assert.equal(star.getAttribute("aria-label"), EN_MESSAGES["conversations.unstar"]);
    assert.equal(star.classList.contains("is-starred"), true);
  } finally {
    await rendered.cleanup();
  }
});

test("conversation detail orders metadata before summary and supports Enter and Escape title editing", async () => {
  const rendered = await renderConversation("normal", true);
  try {
    const metadata = rendered.container.querySelector(".conversation-detail-meta");
    const summary = rendered.container.querySelector(".conversation-summary");
    assert.ok(metadata && summary, "detail renders metadata and summary regions");
    assert.ok(
      metadata.compareDocumentPosition(summary) & rendered.window.Node.DOCUMENT_POSITION_FOLLOWING,
      "metadata precedes the summary in rendered DOM order",
    );
    assert.equal(summary.getAttribute("aria-labelledby"), "conversation-summary-heading");

    const edit = [...rendered.container.querySelectorAll("button")]
      .find((button) => button.textContent?.trim() === EN_MESSAGES["conversations.editTitle"]);
    assert.ok(edit, "detail renders the edit-title affordance");
    await rendered.act(async () => { edit.click(); });
    let input = rendered.container.querySelector(`input[aria-label="${EN_MESSAGES["conversations.editTitle"]}"]`);
    assert.ok(input, "activating edit renders the title input");
    assert.equal(rendered.window.document.activeElement, input, "title input receives focus when it opens");

    await rendered.act(async () => {
      input.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(rendered.container.querySelector(`input[aria-label="${EN_MESSAGES["conversations.editTitle"]}"]`), null);

    const editAgain = [...rendered.container.querySelectorAll("button")]
      .find((button) => button.textContent?.trim() === EN_MESSAGES["conversations.editTitle"]);
    assert.ok(editAgain);
    await rendered.act(async () => { editAgain.click(); });
    input = rendered.container.querySelector(`input[aria-label="${EN_MESSAGES["conversations.editTitle"]}"]`);
    assert.ok(input);
    const setter = Object.getOwnPropertyDescriptor(rendered.window.HTMLInputElement.prototype, "value")?.set;
    assert.ok(setter);
    await rendered.act(async () => {
      setter.call(input, "Renamed in the render test");
      input.dispatchEvent(new rendered.window.Event("input", { bubbles: true }));
      input.dispatchEvent(new rendered.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      await Promise.resolve();
    });
    assert.equal(rendered.container.querySelector(".conversation-detail-title-editor h2")?.textContent, "Renamed in the render test");
  } finally {
    await rendered.cleanup();
  }
});

test("conversation detail renders patch controls only across the canPatch boundary", async () => {
  const permitted = await renderConversation("normal", true);
  try {
    const actions = permitted.container.querySelector(".conversation-detail > .conversation-detail-actions");
    assert.ok(actions, "an unlocked, saved conversation renders its permitted action controls");
    const buttonLabels = [...actions.querySelectorAll("button")].map((button) => button.textContent?.trim());
    assert.ok(buttonLabels.includes(EN_MESSAGES["conversations.unstar"]), "star mutation is available");
    assert.ok(buttonLabels.includes(EN_MESSAGES["conversations.delete"]), "delete mutation is available");
    assert.equal(actions.querySelectorAll("select").length, 2, "visibility and folder mutations are available");
  } finally {
    await permitted.cleanup();
  }

  for (const state of ["locked", "discarded"]) {
    const forbidden = await renderConversation(state, true);
    try {
      assert.equal(
        forbidden.container.querySelector(".conversation-detail > .conversation-detail-actions"),
        null,
        `${state} conversation omits patch controls`,
      );
    } finally {
      await forbidden.cleanup();
    }
  }
  // red-proof: omitting the canPatch action block from a normal detail makes
  // the positive boundary assertion fail; rendering it for locked/discarded fails the negative side.
});

test("conversation dead letters render product copy and never backend summaries", async () => {
  const rendered = await renderConversation("dead");
  try {
    const dead = rendered.container.querySelector(".dead-letter");
    assert.ok(dead, "dead fixture renders its terminal failure");
    assert.ok(dead.textContent?.includes(EN_MESSAGES["dead.body"]));
    assert.equal(dead.textContent?.includes("Update conversation visibility"), false);
    assert.equal(dead.textContent?.includes("The saved conversation change was rejected."), false);
  } finally {
    await rendered.cleanup();
  }
});
