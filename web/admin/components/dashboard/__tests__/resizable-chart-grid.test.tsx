import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  ResizableChartGrid,
  type ChartItem,
} from "@/components/dashboard/resizable-chart-grid";

const items: ChartItem[] = [
  { id: "one", title: "One", render: () => <div>First chart</div> },
  { id: "two", title: "Two", render: () => <div>Second chart</div> },
];

function chartDragData(id: string) {
  const values = new Map<string, string>([
    ["application/x-omi-chart-id", id],
    ["text/plain", id],
  ]);
  const types = Array.from(values.keys());

  return {
    effectAllowed: "move",
    dropEffect: "none",
    types,
    getData: (type: string) => values.get(type) ?? "",
    setData: (type: string, value: string) => {
      values.set(type, value);
      if (!types.includes(type)) types.push(type);
    },
  };
}

describe("ResizableChartGrid drag and drop", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("uses the drag payload to reorder cards and persists the result", async () => {
    const dataTransfer = chartDragData("one");
    const { unmount } = render(
      <ResizableChartGrid storageKey="test:chart-order" items={items} />,
    );
    const target = document.querySelector<HTMLElement>('[data-chart-id="two"]');

    expect(target).not.toBeNull();
    fireEvent.dragStart(screen.getByRole("button", { name: "Move One" }), {
      dataTransfer,
    });
    fireEvent.dragOver(target!, { dataTransfer });
    fireEvent.drop(target!, { dataTransfer });

    await waitFor(() => {
      expect(
        screen
          .getAllByRole("heading", { level: 3 })
          .map((heading) => heading.textContent),
      ).toEqual(["Two", "One"]);
    });
    await waitFor(() => {
      const stored = JSON.parse(
        localStorage.getItem("test:chart-order") ?? "{}",
      );
      expect(stored.order).toEqual(["two", "one"]);
    });

    unmount();
    render(<ResizableChartGrid storageKey="test:chart-order" items={items} />);
    await waitFor(() => {
      expect(
        screen
          .getAllByRole("heading", { level: 3 })
          .map((heading) => heading.textContent),
      ).toEqual(["Two", "One"]);
    });
  });

  it("applies a new default order once while preserving layouts and revealing promoted cards", async () => {
    localStorage.setItem(
      "test:growth-priority",
      JSON.stringify({
        order: ["two", "one"],
        layouts: {
          one: { cols: 6, rows: 4 },
          two: { cols: 3, rows: 2 },
        },
        hidden: ["one"],
        orderRevision: "old-order",
      }),
    );

    const { unmount } = render(
      <ResizableChartGrid
        storageKey="test:growth-priority"
        items={items}
        orderRevision="1m-growth-v1"
        revealOnOrderRevision={["one"]}
      />,
    );

    await waitFor(() => {
      expect(
        screen
          .getAllByRole("heading", { level: 3 })
          .map((heading) => heading.textContent),
      ).toEqual(["One", "Two"]);
    });
    await waitFor(() => {
      const stored = JSON.parse(
        localStorage.getItem("test:growth-priority") ?? "{}",
      );
      expect(stored).toMatchObject({
        order: ["one", "two"],
        layouts: {
          one: { cols: 6, rows: 4 },
          two: { cols: 3, rows: 2 },
        },
        hidden: [],
        orderRevision: "1m-growth-v1",
      });
    });

    localStorage.setItem(
      "test:growth-priority",
      JSON.stringify({
        order: ["two", "one"],
        layouts: {},
        hidden: [],
        orderRevision: "1m-growth-v1",
      }),
    );
    unmount();
    render(
      <ResizableChartGrid
        storageKey="test:growth-priority"
        items={items}
        orderRevision="1m-growth-v1"
        revealOnOrderRevision={["one"]}
      />,
    );

    await waitFor(() => {
      expect(
        screen
          .getAllByRole("heading", { level: 3 })
          .map((heading) => heading.textContent),
      ).toEqual(["Two", "One"]);
    });
  });
});
