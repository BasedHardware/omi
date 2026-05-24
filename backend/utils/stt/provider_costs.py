from dataclasses import dataclass
from typing import Optional

from utils.stt.providers import STTProviderName, STTWorkload


@dataclass(frozen=True)
class PrerecordedProviderCostRate:
    usd_per_billable_second: float
    source: str


# Pay-as-you-go public STT pricing, checked 2026-05-25.
# AssemblyAI background runs use speaker_labels=True, so the pre-recorded
# diarization add-on is included in AssemblyAI rates here. Deepgram background
# runs also request diarize=True, so include the speaker diarization add-on
# there too; otherwise Deepgram appears artificially cheap in rollout gates.
# Customer-specific committed-use discounts are intentionally excluded.
_PRERECORDED_STT_COST_RATES: dict[str, dict[str, PrerecordedProviderCostRate]] = {
    STTProviderName.assemblyai.value: {
        # AssemblyAI pricing: Universal-2 $0.15/hr, Universal-3 Pro $0.21/hr,
        # plus pre-recorded Speaker Diarization $0.02/hr.
        'universal-2': PrerecordedProviderCostRate(
            usd_per_billable_second=0.17 / 3600,
            source='assemblyai_prerecorded_diarized_payg_2026_05_25',
        ),
        'universal-3-pro': PrerecordedProviderCostRate(
            usd_per_billable_second=0.23 / 3600,
            source='assemblyai_prerecorded_diarized_payg_2026_05_25',
        ),
        'u3-pro': PrerecordedProviderCostRate(
            usd_per_billable_second=0.23 / 3600,
            source='assemblyai_prerecorded_diarized_payg_2026_05_25',
        ),
        'default': PrerecordedProviderCostRate(
            usd_per_billable_second=0.17 / 3600,
            source='assemblyai_prerecorded_diarized_default_2026_05_25',
        ),
    },
    STTProviderName.deepgram.value: {
        # Deepgram pricing: Nova-3 monolingual pre-recorded $0.0048/min,
        # Nova-3 multilingual pre-recorded $0.0058/min, plus Speaker
        # Diarization add-on $0.0020/min.
        'nova-3': PrerecordedProviderCostRate(
            usd_per_billable_second=0.0068 / 60,
            source='deepgram_prerecorded_diarized_payg_2026_05_25',
        ),
        'nova-3-general': PrerecordedProviderCostRate(
            usd_per_billable_second=0.0068 / 60,
            source='deepgram_prerecorded_diarized_payg_2026_05_25',
        ),
        'nova-3-multilingual': PrerecordedProviderCostRate(
            usd_per_billable_second=0.0078 / 60,
            source='deepgram_prerecorded_diarized_payg_2026_05_25',
        ),
        'default': PrerecordedProviderCostRate(
            usd_per_billable_second=0.0068 / 60,
            source='deepgram_prerecorded_diarized_default_2026_05_25',
        ),
    },
}

_PRERECORDED_COST_WORKLOADS = {
    STTWorkload.background.value,
    STTWorkload.postprocess.value,
    STTWorkload.ptt.value,
    STTWorkload.sync.value,
    STTWorkload.voice_message.value,
}


def estimate_prerecorded_provider_cost_usd(
    provider: str,
    model: Optional[str],
    workload: str,
    billable_seconds: float,
) -> float:
    if billable_seconds <= 0:
        return 0.0
    if str(workload) not in _PRERECORDED_COST_WORKLOADS:
        return 0.0
    rate = prerecorded_provider_cost_rate(provider, model)
    if not rate:
        return 0.0
    return round(float(billable_seconds) * rate.usd_per_billable_second, 8)


def prerecorded_provider_cost_rate(provider: str, model: Optional[str]) -> Optional[PrerecordedProviderCostRate]:
    provider_rates = _PRERECORDED_STT_COST_RATES.get(str(provider or '').lower())
    if not provider_rates:
        return None
    normalized_model = str(model or '').strip().lower()
    return provider_rates.get(normalized_model) or provider_rates['default']
