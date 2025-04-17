
#include "nimble/porting/nimble/include/syscfg/syscfg.h"
#if MYNEWT_VAL(BLE_MESH)

#include "../include/mesh/mesh.h"
#include "nimble/console/console.h"
#include "light_model.h"


static uint8_t gen_onoff_state;
static int16_t gen_level_state;

static void update_light_state(void)
{
	console_printf("Light state: onoff=%d lvl=0x%04x\n", gen_onoff_state, (uint16_t)gen_level_state);
}

int light_model_gen_onoff_get(struct bt_mesh_model *model, uint8_t *state)
{
	*state = gen_onoff_state;
	return 0;
}

int light_model_gen_onoff_set(struct bt_mesh_model *model, uint8_t state)
{
	gen_onoff_state = state;
	update_light_state();
	return 0;
}

int light_model_gen_level_get(struct bt_mesh_model *model, int16_t *level)
{
	*level = gen_level_state;
	return 0;
}

int light_model_gen_level_set(struct bt_mesh_model *model, int16_t level)
{
	gen_level_state = level;
	if ((uint16_t)gen_level_state > 0x0000) {
		gen_onoff_state = 1;
	}
	if ((uint16_t)gen_level_state == 0x0000) {
		gen_onoff_state = 0;
	}
	update_light_state();
	return 0;
}

int light_model_light_lightness_get(struct bt_mesh_model *model, int16_t *lightness)
{
	return light_model_gen_level_get(model, lightness);
}

int light_model_light_lightness_set(struct bt_mesh_model *model, int16_t lightness)
{
	return light_model_gen_level_set(model, lightness);
}
#endif
