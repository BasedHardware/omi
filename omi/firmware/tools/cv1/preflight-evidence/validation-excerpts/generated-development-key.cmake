19: # Check if PEM file is specified by user, if not, create one a debug key
20: if(NOT SB_CONFIG_SECURE_BOOT_SIGNING_CUSTOM AND "${SB_CONFIG_SECURE_BOOT_SIGNING_KEY_FILE}" STREQUAL "")
21:   message(WARNING "
22:     --------------------------------------------------------------
23:     --- WARNING: Using generated NSIB public/private key-pair. ---
24:     --- It should not be used for production.                  ---
25:     --- See SB_CONFIG_SECURE_BOOT_SIGNING_KEY_FILE             ---
26:     --------------------------------------------------------------
27:     \n"
28:   )
29:
30:   set(DEBUG_SIGN_KEY ${CMAKE_BINARY_DIR}/GENERATED_NON_SECURE_SIGN_KEY_PRIVATE.pem)
31:   set(SIGNATURE_PRIVATE_KEY_FILE ${DEBUG_SIGN_KEY})
32:   add_custom_command(
33:     OUTPUT
34:     ${DEBUG_SIGN_KEY}
35:     COMMAND
36:     ${PRIV_CMD}
37:     --out ${DEBUG_SIGN_KEY}
38:     WORKING_DIRECTORY ${APPLICATION_BINARY_DIR}
39:     COMMENT
40:     "Generating signing key"
