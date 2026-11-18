# Neutral title for a ready recording without notes

Both Home lists can classify a completed batch row as ready and then blank its
stored fallback headline. An unlocked ready row with a batch projection receipt
now displays the neutral label `Recording` when the fallback is its only
display content.

The legacy list applies the Home step projection before building its wire
title. The prepared feed uses that step and the receipt from its existing
document read. With `HOME_STEP_PROJECTION=off`, neither list adds the label.
The label uses no transcript content or time-zone lookup and changes no
stored data. Detail and other non-Home readers keep their current contract.

Verify both lists with a receipt-bearing placeholder row and no preview.
Revert this commit to roll back.
