// Development-only, local fixtures. Production still mounts React Native.
import React from "react";
import { createRoot } from "react-dom/client";
import { Preview } from "./base-ui/Preview";
import { previewDailyIdea, previewOutcomes } from "./base-ui/fixtures";
import "./base-ui/preview.css";

if (import.meta.env.DEV) {
  const params = new URLSearchParams(location.search);
  const data = params.get("data");
  createRoot(document.getElementById("app")!).render(
    <Preview
      initialOutcomes={previewOutcomes(data !== "example")}
      dailyIdea={data === "example" ? previewDailyIdea : null}
      initialPhase={
        data === "error"
          ? "unavailable"
          : data === "loading"
          ? "initial-loading"
          : "ready"
      }
      mobile={
        params.get("surface") === "mobile" ||
        matchMedia("(max-width: 700px)").matches
      }
    />
  );
}
