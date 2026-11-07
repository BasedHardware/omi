"""Every Parakeet-served code and every modulate-only code, cell by cell, through the intake plan.

The supported vocabulary routes exactly like ``en``: safe decisions keep the compute
lane, weak decisions with proven speech flip to the provider lane. Unsupported codes
route exactly like ``ja``. Generated cell names keep the matrix auditable in review."""

from config.batch_pipeline_language import intake_unit_language_plan
from config.prerecorded_language import language_class


def plan(decision, safe, speech):
    return intake_unit_language_plan(
        decision_language=decision,
        parakeet_safe=safe,
        strict_speech=speech,
        input_language='multi',
        language_guard=True,
    )


def test_bg_is_a_supported_code():
    assert language_class('bg') == 'supported'


def test_bg_safe_decision_keeps_compute_lane():
    assert plan('bg', True, None).lane == 'parakeet'


def test_bg_safe_decision_freezes_the_code():
    assert plan('bg', True, True).frozen_language == 'bg'


def test_bg_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('bg', False, True).lane == 'multilingual'


def test_bg_weak_decision_with_speech_freezes_und():
    assert plan('bg', False, True).frozen_language == 'und'


def test_bg_weak_decision_silent_keeps_compute_lane():
    assert plan('bg', False, False).lane == 'parakeet'


def test_cs_is_a_supported_code():
    assert language_class('cs') == 'supported'


def test_cs_safe_decision_keeps_compute_lane():
    assert plan('cs', True, None).lane == 'parakeet'


def test_cs_safe_decision_freezes_the_code():
    assert plan('cs', True, True).frozen_language == 'cs'


def test_cs_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('cs', False, True).lane == 'multilingual'


def test_cs_weak_decision_with_speech_freezes_und():
    assert plan('cs', False, True).frozen_language == 'und'


def test_cs_weak_decision_silent_keeps_compute_lane():
    assert plan('cs', False, False).lane == 'parakeet'


def test_da_is_a_supported_code():
    assert language_class('da') == 'supported'


def test_da_safe_decision_keeps_compute_lane():
    assert plan('da', True, None).lane == 'parakeet'


def test_da_safe_decision_freezes_the_code():
    assert plan('da', True, True).frozen_language == 'da'


def test_da_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('da', False, True).lane == 'multilingual'


def test_da_weak_decision_with_speech_freezes_und():
    assert plan('da', False, True).frozen_language == 'und'


def test_da_weak_decision_silent_keeps_compute_lane():
    assert plan('da', False, False).lane == 'parakeet'


def test_de_is_a_supported_code():
    assert language_class('de') == 'supported'


def test_de_safe_decision_keeps_compute_lane():
    assert plan('de', True, None).lane == 'parakeet'


def test_de_safe_decision_freezes_the_code():
    assert plan('de', True, True).frozen_language == 'de'


def test_de_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('de', False, True).lane == 'multilingual'


def test_de_weak_decision_with_speech_freezes_und():
    assert plan('de', False, True).frozen_language == 'und'


def test_de_weak_decision_silent_keeps_compute_lane():
    assert plan('de', False, False).lane == 'parakeet'


def test_el_is_a_supported_code():
    assert language_class('el') == 'supported'


def test_el_safe_decision_keeps_compute_lane():
    assert plan('el', True, None).lane == 'parakeet'


def test_el_safe_decision_freezes_the_code():
    assert plan('el', True, True).frozen_language == 'el'


def test_el_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('el', False, True).lane == 'multilingual'


def test_el_weak_decision_with_speech_freezes_und():
    assert plan('el', False, True).frozen_language == 'und'


def test_el_weak_decision_silent_keeps_compute_lane():
    assert plan('el', False, False).lane == 'parakeet'


def test_en_is_a_supported_code():
    assert language_class('en') == 'supported'


def test_en_safe_decision_keeps_compute_lane():
    assert plan('en', True, None).lane == 'parakeet'


def test_en_safe_decision_freezes_the_code():
    assert plan('en', True, True).frozen_language == 'en'


def test_en_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('en', False, True).lane == 'multilingual'


def test_en_weak_decision_with_speech_freezes_und():
    assert plan('en', False, True).frozen_language == 'und'


def test_en_weak_decision_silent_keeps_compute_lane():
    assert plan('en', False, False).lane == 'parakeet'


def test_es_is_a_supported_code():
    assert language_class('es') == 'supported'


def test_es_safe_decision_keeps_compute_lane():
    assert plan('es', True, None).lane == 'parakeet'


def test_es_safe_decision_freezes_the_code():
    assert plan('es', True, True).frozen_language == 'es'


def test_es_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('es', False, True).lane == 'multilingual'


def test_es_weak_decision_with_speech_freezes_und():
    assert plan('es', False, True).frozen_language == 'und'


def test_es_weak_decision_silent_keeps_compute_lane():
    assert plan('es', False, False).lane == 'parakeet'


def test_et_is_a_supported_code():
    assert language_class('et') == 'supported'


def test_et_safe_decision_keeps_compute_lane():
    assert plan('et', True, None).lane == 'parakeet'


def test_et_safe_decision_freezes_the_code():
    assert plan('et', True, True).frozen_language == 'et'


def test_et_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('et', False, True).lane == 'multilingual'


def test_et_weak_decision_with_speech_freezes_und():
    assert plan('et', False, True).frozen_language == 'und'


def test_et_weak_decision_silent_keeps_compute_lane():
    assert plan('et', False, False).lane == 'parakeet'


def test_fi_is_a_supported_code():
    assert language_class('fi') == 'supported'


def test_fi_safe_decision_keeps_compute_lane():
    assert plan('fi', True, None).lane == 'parakeet'


def test_fi_safe_decision_freezes_the_code():
    assert plan('fi', True, True).frozen_language == 'fi'


def test_fi_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('fi', False, True).lane == 'multilingual'


def test_fi_weak_decision_with_speech_freezes_und():
    assert plan('fi', False, True).frozen_language == 'und'


def test_fi_weak_decision_silent_keeps_compute_lane():
    assert plan('fi', False, False).lane == 'parakeet'


def test_fr_is_a_supported_code():
    assert language_class('fr') == 'supported'


def test_fr_safe_decision_keeps_compute_lane():
    assert plan('fr', True, None).lane == 'parakeet'


def test_fr_safe_decision_freezes_the_code():
    assert plan('fr', True, True).frozen_language == 'fr'


def test_fr_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('fr', False, True).lane == 'multilingual'


def test_fr_weak_decision_with_speech_freezes_und():
    assert plan('fr', False, True).frozen_language == 'und'


def test_fr_weak_decision_silent_keeps_compute_lane():
    assert plan('fr', False, False).lane == 'parakeet'


def test_hr_is_a_supported_code():
    assert language_class('hr') == 'supported'


def test_hr_safe_decision_keeps_compute_lane():
    assert plan('hr', True, None).lane == 'parakeet'


def test_hr_safe_decision_freezes_the_code():
    assert plan('hr', True, True).frozen_language == 'hr'


def test_hr_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('hr', False, True).lane == 'multilingual'


def test_hr_weak_decision_with_speech_freezes_und():
    assert plan('hr', False, True).frozen_language == 'und'


def test_hr_weak_decision_silent_keeps_compute_lane():
    assert plan('hr', False, False).lane == 'parakeet'


def test_hu_is_a_supported_code():
    assert language_class('hu') == 'supported'


def test_hu_safe_decision_keeps_compute_lane():
    assert plan('hu', True, None).lane == 'parakeet'


def test_hu_safe_decision_freezes_the_code():
    assert plan('hu', True, True).frozen_language == 'hu'


def test_hu_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('hu', False, True).lane == 'multilingual'


def test_hu_weak_decision_with_speech_freezes_und():
    assert plan('hu', False, True).frozen_language == 'und'


def test_hu_weak_decision_silent_keeps_compute_lane():
    assert plan('hu', False, False).lane == 'parakeet'


def test_it_is_a_supported_code():
    assert language_class('it') == 'supported'


def test_it_safe_decision_keeps_compute_lane():
    assert plan('it', True, None).lane == 'parakeet'


def test_it_safe_decision_freezes_the_code():
    assert plan('it', True, True).frozen_language == 'it'


def test_it_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('it', False, True).lane == 'multilingual'


def test_it_weak_decision_with_speech_freezes_und():
    assert plan('it', False, True).frozen_language == 'und'


def test_it_weak_decision_silent_keeps_compute_lane():
    assert plan('it', False, False).lane == 'parakeet'


def test_lt_is_a_supported_code():
    assert language_class('lt') == 'supported'


def test_lt_safe_decision_keeps_compute_lane():
    assert plan('lt', True, None).lane == 'parakeet'


def test_lt_safe_decision_freezes_the_code():
    assert plan('lt', True, True).frozen_language == 'lt'


def test_lt_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('lt', False, True).lane == 'multilingual'


def test_lt_weak_decision_with_speech_freezes_und():
    assert plan('lt', False, True).frozen_language == 'und'


def test_lt_weak_decision_silent_keeps_compute_lane():
    assert plan('lt', False, False).lane == 'parakeet'


def test_lv_is_a_supported_code():
    assert language_class('lv') == 'supported'


def test_lv_safe_decision_keeps_compute_lane():
    assert plan('lv', True, None).lane == 'parakeet'


def test_lv_safe_decision_freezes_the_code():
    assert plan('lv', True, True).frozen_language == 'lv'


def test_lv_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('lv', False, True).lane == 'multilingual'


def test_lv_weak_decision_with_speech_freezes_und():
    assert plan('lv', False, True).frozen_language == 'und'


def test_lv_weak_decision_silent_keeps_compute_lane():
    assert plan('lv', False, False).lane == 'parakeet'


def test_mt_is_a_supported_code():
    assert language_class('mt') == 'supported'


def test_mt_safe_decision_keeps_compute_lane():
    assert plan('mt', True, None).lane == 'parakeet'


def test_mt_safe_decision_freezes_the_code():
    assert plan('mt', True, True).frozen_language == 'mt'


def test_mt_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('mt', False, True).lane == 'multilingual'


def test_mt_weak_decision_with_speech_freezes_und():
    assert plan('mt', False, True).frozen_language == 'und'


def test_mt_weak_decision_silent_keeps_compute_lane():
    assert plan('mt', False, False).lane == 'parakeet'


def test_nl_is_a_supported_code():
    assert language_class('nl') == 'supported'


def test_nl_safe_decision_keeps_compute_lane():
    assert plan('nl', True, None).lane == 'parakeet'


def test_nl_safe_decision_freezes_the_code():
    assert plan('nl', True, True).frozen_language == 'nl'


def test_nl_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('nl', False, True).lane == 'multilingual'


def test_nl_weak_decision_with_speech_freezes_und():
    assert plan('nl', False, True).frozen_language == 'und'


def test_nl_weak_decision_silent_keeps_compute_lane():
    assert plan('nl', False, False).lane == 'parakeet'


def test_pl_is_a_supported_code():
    assert language_class('pl') == 'supported'


def test_pl_safe_decision_keeps_compute_lane():
    assert plan('pl', True, None).lane == 'parakeet'


def test_pl_safe_decision_freezes_the_code():
    assert plan('pl', True, True).frozen_language == 'pl'


def test_pl_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('pl', False, True).lane == 'multilingual'


def test_pl_weak_decision_with_speech_freezes_und():
    assert plan('pl', False, True).frozen_language == 'und'


def test_pl_weak_decision_silent_keeps_compute_lane():
    assert plan('pl', False, False).lane == 'parakeet'


def test_pt_is_a_supported_code():
    assert language_class('pt') == 'supported'


def test_pt_safe_decision_keeps_compute_lane():
    assert plan('pt', True, None).lane == 'parakeet'


def test_pt_safe_decision_freezes_the_code():
    assert plan('pt', True, True).frozen_language == 'pt'


def test_pt_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('pt', False, True).lane == 'multilingual'


def test_pt_weak_decision_with_speech_freezes_und():
    assert plan('pt', False, True).frozen_language == 'und'


def test_pt_weak_decision_silent_keeps_compute_lane():
    assert plan('pt', False, False).lane == 'parakeet'


def test_ro_is_a_supported_code():
    assert language_class('ro') == 'supported'


def test_ro_safe_decision_keeps_compute_lane():
    assert plan('ro', True, None).lane == 'parakeet'


def test_ro_safe_decision_freezes_the_code():
    assert plan('ro', True, True).frozen_language == 'ro'


def test_ro_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('ro', False, True).lane == 'multilingual'


def test_ro_weak_decision_with_speech_freezes_und():
    assert plan('ro', False, True).frozen_language == 'und'


def test_ro_weak_decision_silent_keeps_compute_lane():
    assert plan('ro', False, False).lane == 'parakeet'


def test_ru_is_a_supported_code():
    assert language_class('ru') == 'supported'


def test_ru_safe_decision_keeps_compute_lane():
    assert plan('ru', True, None).lane == 'parakeet'


def test_ru_safe_decision_freezes_the_code():
    assert plan('ru', True, True).frozen_language == 'ru'


def test_ru_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('ru', False, True).lane == 'multilingual'


def test_ru_weak_decision_with_speech_freezes_und():
    assert plan('ru', False, True).frozen_language == 'und'


def test_ru_weak_decision_silent_keeps_compute_lane():
    assert plan('ru', False, False).lane == 'parakeet'


def test_sk_is_a_supported_code():
    assert language_class('sk') == 'supported'


def test_sk_safe_decision_keeps_compute_lane():
    assert plan('sk', True, None).lane == 'parakeet'


def test_sk_safe_decision_freezes_the_code():
    assert plan('sk', True, True).frozen_language == 'sk'


def test_sk_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('sk', False, True).lane == 'multilingual'


def test_sk_weak_decision_with_speech_freezes_und():
    assert plan('sk', False, True).frozen_language == 'und'


def test_sk_weak_decision_silent_keeps_compute_lane():
    assert plan('sk', False, False).lane == 'parakeet'


def test_sl_is_a_supported_code():
    assert language_class('sl') == 'supported'


def test_sl_safe_decision_keeps_compute_lane():
    assert plan('sl', True, None).lane == 'parakeet'


def test_sl_safe_decision_freezes_the_code():
    assert plan('sl', True, True).frozen_language == 'sl'


def test_sl_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('sl', False, True).lane == 'multilingual'


def test_sl_weak_decision_with_speech_freezes_und():
    assert plan('sl', False, True).frozen_language == 'und'


def test_sl_weak_decision_silent_keeps_compute_lane():
    assert plan('sl', False, False).lane == 'parakeet'


def test_sv_is_a_supported_code():
    assert language_class('sv') == 'supported'


def test_sv_safe_decision_keeps_compute_lane():
    assert plan('sv', True, None).lane == 'parakeet'


def test_sv_safe_decision_freezes_the_code():
    assert plan('sv', True, True).frozen_language == 'sv'


def test_sv_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('sv', False, True).lane == 'multilingual'


def test_sv_weak_decision_with_speech_freezes_und():
    assert plan('sv', False, True).frozen_language == 'und'


def test_sv_weak_decision_silent_keeps_compute_lane():
    assert plan('sv', False, False).lane == 'parakeet'


def test_uk_is_a_supported_code():
    assert language_class('uk') == 'supported'


def test_uk_safe_decision_keeps_compute_lane():
    assert plan('uk', True, None).lane == 'parakeet'


def test_uk_safe_decision_freezes_the_code():
    assert plan('uk', True, True).frozen_language == 'uk'


def test_uk_weak_decision_with_speech_takes_the_provider_lane():
    assert plan('uk', False, True).lane == 'multilingual'


def test_uk_weak_decision_with_speech_freezes_und():
    assert plan('uk', False, True).frozen_language == 'und'


def test_uk_weak_decision_silent_keeps_compute_lane():
    assert plan('uk', False, False).lane == 'parakeet'


def test_af_is_an_unsupported_code():
    assert language_class('af') == 'unsupported'


def test_af_detected_speech_takes_the_provider_lane():
    assert plan('af', False, True).lane == 'multilingual'


def test_af_detected_speech_freezes_the_code():
    assert plan('af', False, True).frozen_language == 'af'


def test_af_detected_silence_keeps_compute_lane():
    assert plan('af', False, False).lane == 'parakeet'


def test_ar_is_an_unsupported_code():
    assert language_class('ar') == 'unsupported'


def test_ar_detected_speech_takes_the_provider_lane():
    assert plan('ar', False, True).lane == 'multilingual'


def test_ar_detected_speech_freezes_the_code():
    assert plan('ar', False, True).frozen_language == 'ar'


def test_ar_detected_silence_keeps_compute_lane():
    assert plan('ar', False, False).lane == 'parakeet'


def test_az_is_an_unsupported_code():
    assert language_class('az') == 'unsupported'


def test_az_detected_speech_takes_the_provider_lane():
    assert plan('az', False, True).lane == 'multilingual'


def test_az_detected_speech_freezes_the_code():
    assert plan('az', False, True).frozen_language == 'az'


def test_az_detected_silence_keeps_compute_lane():
    assert plan('az', False, False).lane == 'parakeet'


def test_be_is_an_unsupported_code():
    assert language_class('be') == 'unsupported'


def test_be_detected_speech_takes_the_provider_lane():
    assert plan('be', False, True).lane == 'multilingual'


def test_be_detected_speech_freezes_the_code():
    assert plan('be', False, True).frozen_language == 'be'


def test_be_detected_silence_keeps_compute_lane():
    assert plan('be', False, False).lane == 'parakeet'


def test_bn_is_an_unsupported_code():
    assert language_class('bn') == 'unsupported'


def test_bn_detected_speech_takes_the_provider_lane():
    assert plan('bn', False, True).lane == 'multilingual'


def test_bn_detected_speech_freezes_the_code():
    assert plan('bn', False, True).frozen_language == 'bn'


def test_bn_detected_silence_keeps_compute_lane():
    assert plan('bn', False, False).lane == 'parakeet'


def test_bs_is_an_unsupported_code():
    assert language_class('bs') == 'unsupported'


def test_bs_detected_speech_takes_the_provider_lane():
    assert plan('bs', False, True).lane == 'multilingual'


def test_bs_detected_speech_freezes_the_code():
    assert plan('bs', False, True).frozen_language == 'bs'


def test_bs_detected_silence_keeps_compute_lane():
    assert plan('bs', False, False).lane == 'parakeet'


def test_ca_is_an_unsupported_code():
    assert language_class('ca') == 'unsupported'


def test_ca_detected_speech_takes_the_provider_lane():
    assert plan('ca', False, True).lane == 'multilingual'


def test_ca_detected_speech_freezes_the_code():
    assert plan('ca', False, True).frozen_language == 'ca'


def test_ca_detected_silence_keeps_compute_lane():
    assert plan('ca', False, False).lane == 'parakeet'


def test_cy_is_an_unsupported_code():
    assert language_class('cy') == 'unsupported'


def test_cy_detected_speech_takes_the_provider_lane():
    assert plan('cy', False, True).lane == 'multilingual'


def test_cy_detected_speech_freezes_the_code():
    assert plan('cy', False, True).frozen_language == 'cy'


def test_cy_detected_silence_keeps_compute_lane():
    assert plan('cy', False, False).lane == 'parakeet'


def test_und_detected_speech_takes_the_provider_lane():
    assert plan('und', False, True).lane == 'multilingual'


def test_multi_detected_speech_takes_the_provider_lane():
    assert plan('multi', False, True).lane == 'multilingual'


def test_blank_detected_speech_takes_the_provider_lane():
    assert plan('', False, True).lane == 'multilingual'


def test_und_detected_speech_freezes_und():
    assert plan('und', False, True).frozen_language == 'und'


def test_multi_detected_speech_freezes_und():
    assert plan('multi', False, True).frozen_language == 'und'


def test_blank_detected_speech_freezes_und():
    assert plan('', False, True).frozen_language == 'und'


def test_unsupported_and_unknown_lanes_agree_only_through_speech():
    for code in ('und', '', 'multi'):
        assert plan(code, False, True).lane == plan('ja', False, True).lane == 'multilingual'


def test_every_supported_code_matches_the_en_cell_shape():
    for code in [
        'bg',
        'cs',
        'da',
        'de',
        'el',
        'en',
        'es',
        'et',
        'fi',
        'fr',
        'hr',
        'hu',
        'it',
        'lt',
        'lv',
        'mt',
        'nl',
        'pl',
        'pt',
        'ro',
        'ru',
        'sk',
        'sl',
        'sv',
        'uk',
    ]:
        assert plan(code, False, True).lane == plan('en', False, True).lane
        assert plan(code, False, False).lane == plan('en', False, False).lane
