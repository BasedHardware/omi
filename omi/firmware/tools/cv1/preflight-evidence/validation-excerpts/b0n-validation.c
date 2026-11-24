197: #if defined(CONFIG_SB_VALIDATE_FW_SIGNATURE)
198: static bool validate_signature(const uint32_t fw_src_address, const uint32_t fw_size,
199: 			       const struct fw_validation_info *fw_val_info,
200: 			       bool external)
201: {
202: 	int init_retval = bl_crypto_init();
203:
204: 	if (init_retval) {
273:
274: #elif defined(CONFIG_SB_VALIDATE_FW_HASH)
275: static bool validate_hash(const uint32_t fw_src_address, const uint32_t fw_size,
276: 			  const struct fw_validation_info *fw_val_info,
277: 			  bool external)
278: {
279: 	int retval = bl_crypto_init();
280:
281: 	if (retval) {
282: 		LOG_ERR("bl_crypto_init() returned %d.", retval);
283: 		return false;
284: 	}
285:
286: 	retval = bl_sha256_verify((const uint8_t *)fw_src_address, fw_size,
287: 			fw_val_info->hash);
288:
289: 	if (retval != 0) {
290: 		LOG_ERR("Firmware validation failed with error %d.",
291: 			retval);
292: 		return false;
293: 	}
294:
295: 	LOG_INF("Firmware hash verified.");
296:
297: 	return true;
298: }
299: #endif
300:
417: #if defined(CONFIG_SB_VALIDATE_FW_SIGNATURE)
418: 	return validate_signature(fw_src_address, fwinfo->size, fw_val_info,
419: 				external);
420: #elif defined(CONFIG_SB_VALIDATE_FW_HASH)
421: 	return validate_hash(fw_src_address, fwinfo->size, fw_val_info,
422: 				external);
423: #else
