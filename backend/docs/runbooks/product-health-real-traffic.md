# Product health — real traffic

## Scope

This dashboard and its alert rules use accepted user traffic only; they do not
generate synthetic traffic. Dev and production are isolated by Prometheus
instance, not by an environment label. Each current success rate is compared
only with the 24-hour offset data held by that same Prometheus instance.

## Chat response regression alert

`product_health_chat_response_regression` pages only when more than 20 chat
streams were accepted in 15 minutes, the current success rate is below 80%,
and it is at least 20 percentage points below its own 24-hour baseline for 15
minutes. Check the Product health — real traffic dashboard panel before
triaging provider, application, or scrape failures.

## Current false-negative limits

- Low traffic is intentionally gated and will not alert, including a complete
  outage with 20 or fewer accepted chat streams in a 15-minute window.
- A missing 24-hour baseline, such as after a new Prometheus instance or
  retention gap, suppresses the regression comparison.
- `noDataState: OK` means a scrape gap can look healthy; verify targets before
  declaring recovery.
- This measures only streams accepted by the backend. Requests rejected before
  the stream boundary and clients that never reach the service are out of
  scope.
