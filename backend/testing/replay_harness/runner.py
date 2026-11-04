"""Load case directories, execute selected boundaries, and record explicit stops."""

from contextlib import ExitStack
from pathlib import Path
import time

from testing.replay_harness.manifest import STAGES, load_case
from testing.replay_harness.report import StageResult, item_report, record_exception
from testing.replay_harness.stages.base import NotImplementedStage


async def run_cases(directories: list[Path]) -> list[dict]:
    # Validate all inputs before constructing any infrastructure.
    cases = [load_case(directory) for directory in directories]
    if len({case.manifest.id for case in cases}) != len(cases):
        raise ValueError('duplicate case id would overwrite an item report')
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.stages.admission import AdmissionDriver
    from testing.replay_harness.stages.capture_upload import CaptureUploadDriver
    from testing.replay_harness.stages.finalization import TitlingDriver
    from testing.replay_harness.stages.episodes import EpisodesDriver

    from testing.replay_harness.stages.privacy_cache import PrivacyCacheDriver

    items = []
    for case in cases:
        results = []
        with ExitStack() as stack:
            environment = None
            for name in STAGES:
                if name not in (case.manifest.stages or {'capture_upload': {}, 'titling': {}}):
                    continue
                driver = {
                    'admission': AdmissionDriver,
                    'capture_upload': CaptureUploadDriver,
                    'titling': TitlingDriver,
                    'episodes': EpisodesDriver,
                    'privacy_cache': PrivacyCacheDriver,
                }.get(name, lambda: NotImplementedStage(name))()
                # Privacy timelines own one isolated emulator/Redis context per
                # transition. Close any preceding pipeline environment first.
                if name == 'privacy_cache':
                    stack.close()
                    environment = None
                elif environment is None:
                    environment = stack.enter_context(replay_environment())
                started = time.perf_counter()
                try:
                    result = await driver.run(case, environment)
                except Exception as error:
                    result = StageResult(name, 'stopped', **record_exception(error, name))
                result.duration_ms = round((time.perf_counter() - started) * 1000, 3)
                results.append(result)
                if result.status != 'pass':
                    break
        items.append(item_report(case.manifest, results))
    return items
