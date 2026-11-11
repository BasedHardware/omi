import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PeriodChangeIndicator } from "@/components/dashboard/period-change-indicator";

describe("PeriodChangeIndicator", () => {
  it("shows a positive change in green with comparison context", () => {
    render(
      <PeriodChangeIndicator
        change={{ percentage: 20, label: "vs previous week" }}
      />,
    );

    const indicator = screen.getByLabelText("+20% vs previous week");
    expect(indicator.textContent).toBe("+20%");
    expect(indicator.classList.contains("text-green-600")).toBe(true);
  });

  it("shows a negative change in red", () => {
    render(
      <PeriodChangeIndicator
        change={{ percentage: -12.5, label: "vs previous day" }}
      />,
    );

    expect(
      screen
        .getByLabelText("-13% vs previous day")
        .classList.contains("text-red-600"),
    ).toBe(true);
  });
});
