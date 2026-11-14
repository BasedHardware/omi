import { main } from "./live";

if (process.argv.includes("--help"))
  console.info(
    "Omi TV live metered cost: meters yesterday and today (UTC) with a 5-minute lag and writes the live document"
  );
else
  main().catch(() => {
    // Monitoring/SDK errors can carry request detail. Emit a controlled failure.
    console.error(
      JSON.stringify({ event: "wall_live_job", outcome: "failed" })
    );
    process.exitCode = 1;
  });
