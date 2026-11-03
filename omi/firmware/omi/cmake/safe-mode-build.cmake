# Release entrypoints never set OMI_DEVELOPMENT_BUILD. Fail closed even if an
# overlay manually sets the fault option; CONFIG_DEBUG alone is insufficient.
if(CONFIG_OMI_FAULT_INJECT)
  if(NOT OMI_DEVELOPMENT_BUILD OR NOT CONFIG_DEBUG OR CMAKE_BUILD_TYPE MATCHES "^(Release|RelWithDebInfo|MinSizeRel)$")
    message(FATAL_ERROR "OMI_FAULT_INJECT is forbidden in release builds; use DEBUG and OMI_DEVELOPMENT_BUILD for jig builds")
  endif()
  if(TARGET app)
    target_compile_definitions(app PRIVATE OMI_FAULT_INJECT_ALLOWED=1)
  endif()
endif()

if(CONFIG_MCUMGR AND (NOT CONFIG_MCUMGR_MGMT_NOTIFICATION_HOOKS OR NOT CONFIG_MCUMGR_GRP_IMG_STATUS_HOOKS))
  message(FATAL_ERROR "Safe-mode recovery requires MCUmgr notification and image status hooks")
endif()
