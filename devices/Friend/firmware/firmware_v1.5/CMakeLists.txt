# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nrf52840_nordic)
enable_language(C ASM)

target_sources(app PRIVATE
    src/main.c
    src/transport.c
    src/mic.c
    src/led.c
    src/audio.c
    src/codec.c
    src/camera.c
    src/controls.c
    src/battery.c
    src/settings.c
)

target_sources_ifdef(CONFIG_BUBBLE_CODEC_OPUS app PRIVATE
    src/opus-1.2.1/A2NLSF.c
    src/opus-1.2.1/CNG.c
    src/opus-1.2.1/HP_variable_cutoff.c
    src/opus-1.2.1/LPC_analysis_filter.c
    src/opus-1.2.1/LPC_fit.c
    src/opus-1.2.1/LPC_inv_pred_gain.c
    src/opus-1.2.1/LP_variable_cutoff.c
    src/opus-1.2.1/LTP_analysis_filter_FIX.c
    src/opus-1.2.1/LTP_scale_ctrl_FIX.c
    src/opus-1.2.1/NLSF2A.c
    src/opus-1.2.1/NLSF_VQ.c
    src/opus-1.2.1/NLSF_VQ_weights_laroia.c
    src/opus-1.2.1/NLSF_decode.c
    src/opus-1.2.1/NLSF_del_dec_quant.c
    src/opus-1.2.1/NLSF_encode.c
    src/opus-1.2.1/NLSF_stabilize.c
    src/opus-1.2.1/NLSF_unpack.c
    src/opus-1.2.1/NSQ.c
    src/opus-1.2.1/NSQ_del_dec.c
    src/opus-1.2.1/PLC.c
    src/opus-1.2.1/VAD.c
    src/opus-1.2.1/VQ_WMat_EC.c
    src/opus-1.2.1/ana_filt_bank_1.c
    src/opus-1.2.1/analysis.c
    src/opus-1.2.1/apply_sine_window_FIX.c
    src/opus-1.2.1/autocorr_FIX.c
    src/opus-1.2.1/bands.c
    src/opus-1.2.1/biquad_alt.c
    src/opus-1.2.1/burg_modified_FIX.c
    src/opus-1.2.1/bwexpander.c
    src/opus-1.2.1/bwexpander_32.c
    src/opus-1.2.1/celt.c
    src/opus-1.2.1/celt_decoder.c
    src/opus-1.2.1/celt_encoder.c
    src/opus-1.2.1/celt_lpc.c
    src/opus-1.2.1/arm/celt_pitch_xcorr_arm_gcc.s
    src/opus-1.2.1/check_control_input.c
    src/opus-1.2.1/code_signs.c
    src/opus-1.2.1/control_SNR.c
    src/opus-1.2.1/control_audio_bandwidth.c
    src/opus-1.2.1/control_codec.c
    src/opus-1.2.1/corrMatrix_FIX.c
    src/opus-1.2.1/cwrs.c
    src/opus-1.2.1/debug.c
    src/opus-1.2.1/dec_API.c
    src/opus-1.2.1/decode_core.c
    src/opus-1.2.1/decode_frame.c
    src/opus-1.2.1/decode_indices.c
    src/opus-1.2.1/decode_parameters.c
    src/opus-1.2.1/decode_pitch.c
    src/opus-1.2.1/decode_pulses.c
    src/opus-1.2.1/decoder_set_fs.c
    src/opus-1.2.1/enc_API.c
    src/opus-1.2.1/encode_frame_FIX.c
    src/opus-1.2.1/encode_indices.c
    src/opus-1.2.1/encode_pulses.c
    src/opus-1.2.1/entcode.c
    src/opus-1.2.1/entdec.c
    src/opus-1.2.1/entenc.c
    src/opus-1.2.1/find_LPC_FIX.c
    src/opus-1.2.1/find_LTP_FIX.c
    src/opus-1.2.1/find_pitch_lags_FIX.c
    src/opus-1.2.1/find_pred_coefs_FIX.c
    src/opus-1.2.1/gain_quant.c
    src/opus-1.2.1/init_decoder.c
    src/opus-1.2.1/init_encoder.c
    src/opus-1.2.1/inner_prod_aligned.c
    src/opus-1.2.1/interpolate.c
    src/opus-1.2.1/k2a_FIX.c
    src/opus-1.2.1/k2a_Q16_FIX.c
    src/opus-1.2.1/kiss_fft.c
    src/opus-1.2.1/laplace.c
    src/opus-1.2.1/lin2log.c
    src/opus-1.2.1/log2lin.c
    src/opus-1.2.1/mathops.c
    src/opus-1.2.1/mdct.c
    src/opus-1.2.1/mlp.c
    src/opus-1.2.1/mlp_data.c
    src/opus-1.2.1/modes.c
    src/opus-1.2.1/noise_shape_analysis_FIX.c
    src/opus-1.2.1/opus.c
    src/opus-1.2.1/opus_decoder.c
    src/opus-1.2.1/opus_encoder.c
    src/opus-1.2.1/opus_multistream.c
    src/opus-1.2.1/opus_multistream_decoder.c
    src/opus-1.2.1/opus_multistream_encoder.c
    src/opus-1.2.1/pitch.c
    src/opus-1.2.1/pitch_analysis_core_FIX.c
    src/opus-1.2.1/pitch_est_tables.c
    src/opus-1.2.1/process_NLSFs.c
    src/opus-1.2.1/process_gains_FIX.c
    src/opus-1.2.1/quant_LTP_gains.c
    src/opus-1.2.1/quant_bands.c
    src/opus-1.2.1/rate.c
    src/opus-1.2.1/regularize_correlations_FIX.c
    src/opus-1.2.1/repacketizer.c
    src/opus-1.2.1/resampler.c
    src/opus-1.2.1/resampler_down2.c
    src/opus-1.2.1/resampler_down2_3.c
    src/opus-1.2.1/resampler_private_AR2.c
    src/opus-1.2.1/resampler_private_IIR_FIR.c
    src/opus-1.2.1/resampler_private_down_FIR.c
    src/opus-1.2.1/resampler_private_up2_HQ.c
    src/opus-1.2.1/resampler_rom.c
    src/opus-1.2.1/residual_energy16_FIX.c
    src/opus-1.2.1/residual_energy_FIX.c
    src/opus-1.2.1/schur64_FIX.c
    src/opus-1.2.1/schur_FIX.c
    src/opus-1.2.1/shell_coder.c
    src/opus-1.2.1/sigm_Q15.c
    src/opus-1.2.1/sort.c
    src/opus-1.2.1/stereo_LR_to_MS.c
    src/opus-1.2.1/stereo_MS_to_LR.c
    src/opus-1.2.1/stereo_decode_pred.c
    src/opus-1.2.1/stereo_encode_pred.c
    src/opus-1.2.1/stereo_find_predictor.c
    src/opus-1.2.1/stereo_quant_pred.c
    src/opus-1.2.1/sum_sqr_shift.c
    src/opus-1.2.1/table_LSF_cos.c
    src/opus-1.2.1/tables_LTP.c
    src/opus-1.2.1/tables_NLSF_CB_NB_MB.c
    src/opus-1.2.1/tables_NLSF_CB_WB.c
    src/opus-1.2.1/tables_gain.c
    src/opus-1.2.1/tables_other.c
    src/opus-1.2.1/tables_pitch_lag.c
    src/opus-1.2.1/tables_pulses_per_block.c
    src/opus-1.2.1/vector_ops_FIX.c
    src/opus-1.2.1/vq.c
    src/opus-1.2.1/warped_autocorrelation_FIX.c
    src/opus-1.2.1/arm/celt_pitch_xcorr_arm_gcc.s
)

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DARM_MATH_CM4")
# set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DVAR_ARRAYS")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_ASM")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_INLINE_ASM")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_INLINE_EDSP")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_INLINE_MEDIA")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_MAY_HAVE_EDSP")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_ARM_PRESUME_EDSP")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DOPUS_BUILD")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DUSE_ALLOCA")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DFIXED_POINT -DDISABLE_FLOAT_API")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_CONFIG_H")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_ALLOCA_H")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fsingle-precision-constant") # A lot of constants are written as doubles
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DHAVE_LRINT -DHAVE_LRINTF")