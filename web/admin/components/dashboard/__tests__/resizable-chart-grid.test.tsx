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
});
