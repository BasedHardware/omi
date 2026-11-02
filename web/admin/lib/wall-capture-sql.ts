/** Shared audited capture evidence; used by HogQL and the daily writer. */
export function captureEvidenceCtes() {
  const family = (name: string, fam: string[], type: string[] = []) =>
    `dev AND (fam IN (${fam.map((f) => `'${f}'`).join(",")})${
      type.length
        ? ` OR properties.type IN (${type.map((t) => `'${t}'`).join(",")})`
        : ""
    }),'${name}'`;
  return `    cls AS (SELECT *,
      if(event='Memory Created' AND p IN ('ios','android'),parseDateTimeBestEffort(coalesce(toString(properties.timestamp),'1970-01-01')),timestamp) et,
      (event='Memory Created' AND properties.memory_result='saved' AND toString(properties.memory_discarded)='false' AND properties.memory_id IS NOT NULL) saved_mem,
      event IN ('Device Connected','Device Paired','Device Session Ended') dev,
      coalesce(toString(properties.hardware_family),'') fam,
      coalesce(toString(properties.conversation_source),'') src FROM qualified),
    hw AS (SELECT *,multiIf(${family("Omi pendant", ["omi_cv1"])},
      ${family("Omi Neo", ["omi_neo"])},${family("Omi devkit", [
    "omi_devkit",
    "friend_devkit",
  ])},
      ${family("Omi Glass", ["omi_glass"], ["openglass"])},${family(
    "Apple Watch",
    ["apple_watch"],
    ["appleWatch"]
  )},
      ${family("Plaud", ["plaud"], ["plaud"])},${family(
    "Bee",
    ["bee"],
    ["bee"]
  )},${family("Fieldy", ["fieldy"], ["fieldy"])},
      ${family(
        "Friend pendant",
        ["friend_pendant"],
        ["friendPendant"]
      )},${family("Limitless", ["limitless"], ["limitless"])},
      ${family(
        "Ray-Ban Meta",
        ["rayban_meta"],
        ["raybanMeta"]
      )},dev AND properties.type='omi','Omi unspecified',
      saved_mem AND src='omi','Omi unspecified',saved_mem AND src='openglass','Omi Glass',saved_mem AND src='apple_watch','Apple Watch',
      saved_mem AND src='limitless','Limitless',saved_mem AND src='fieldy','Fieldy',saved_mem AND src='bee','Bee',
      saved_mem AND src='friend_com','Friend pendant',saved_mem AND src='rayban_meta','Ray-Ban Meta',
      saved_mem AND properties.recording_hardware_type='plaud','Plaud','') h,
      (event='Phone Mic Recording Started' OR (saved_mem AND src='phone')) phone,
      ((event='Memory Created' AND src='desktop') OR event='Desktop Recording Started') mac FROM cls)`;
}
