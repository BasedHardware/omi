import { main } from "./writer";

if (process.argv.includes("--help"))
  console.info(
    "Omi TV daily rollup; optional OMI_TV_ROLLUP_DATE=YYYY-MM-DD for one closed day"
  );
else
  main().catch(() => {
    // SDK/network errors may contain request bodies. Emit a controlled failure.
    console.error(
      JSON.stringify({ event: "wall_rollup_job", outcome: "failed" })
    );
    process.exitCode = 1;
  });
