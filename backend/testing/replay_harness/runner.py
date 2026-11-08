"""Load case directories, execute selected boundaries, and record explicit stops."""

from contextlib import ExitStack
from pathlib import Path
import time

from testing.replay_harness.manifest import STAGES, load_case
from testing.replay_harness.decryption import load_decryption, opaque_firestore, product_decryption, quiet_product
from testing.replay_harness.report import StageResult, item_report, record_exception
from testing.replay_harness.stages.base import NotImplementedStage


async def run_cases(
    directories: list[Path],
    *,
    privacy_ttl_override_s=None,
    secret_file=None,
    uid_file=None,
    consent_file=None,
    runtime_env=None,
    runtime_backend=None
) -> list[dict]:
    from testing.replay_harness.runtime_env import load_runtime_env

    runtime_config = load_runtime_env(runtime_env, backend=runtime_backend)
    # Validate all inputs before constructing any infrastructure.
    cases = [load_case(directory) for directory in directories]
    if len({case.manifest.id for case in cases}) != len(cases):
        raise ValueError('duplicate case id would overwrite an item report')
    credentials = load_decryption(secret_file=secret_file, uid_file=uid_file, consent_file=consent_file)
    if credentials:
        for case in cases:
            credentials.validate(case)
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.stages.admission import AdmissionDriver
    from testing.replay_harness.stages.capture_upload import CaptureUploadDriver
    from testing.replay_harness.stages.finalization import TitlingDriver
    from testing.replay_harness.stages.episodes import EpisodesDriver

    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    items = []
    for case in cases:
        results = []
        enabled = credentials is not None and case.manifest.tier == 'C'
        with ExitStack() as stack:
            if enabled:
                stack.enter_context(quiet_product())
                stack.enter_context(opaque_firestore())
            environment = None
            for name in STAGES:
                if name not in (case.manifest.stages or {'capture_upload': {}, 'titling': {}}):
                    continue
                driver = {
                    'admission': AdmissionDriver,
                    'capture_upload': CaptureUploadDriver,
                    'titling': TitlingDriver,
                    'episodes': EpisodesDriver,
                    'privacy_cache': lambda: PrivacyCacheDriver(
                        ttl_override_s=privacy_ttl_override_s, runtime_env=runtime_config
                    ),
                }.get(name, lambda: NotImplementedStage(name))()
                # Privacy timelines own one isolated emulator/Redis context per
                # transition. Close any preceding pipeline environment first.
                if name == 'privacy_cache':
                    stack.close()
                    environment = None
                elif environment is None:
                    environment = stack.enter_context(replay_environment(runtime_config))
                    if enabled:
                        stack.enter_context(product_decryption(case, environment, credentials))
                started = time.perf_counter()
                try:
                    result = await driver.run(case, environment)
                except Exception as error:
                    result = StageResult(name, 'stopped', **record_exception(error, name))
                result.duration_ms = round((time.perf_counter() - started) * 1000, 3)
                results.append(result)
                if result.status != 'pass':
                    break
        item = item_report(case.manifest, results, decryption='on' if enabled else 'off')
        if runtime_config is not None:
            item['runtime_env'] = runtime_config.report()
        items.append(item)
    return items
