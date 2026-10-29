import sys
sys.path.append("backend")
import os
from config.refactor_modes import shadow_sampled
os.environ["EPISODE_BOUNDARIES_MODE"] = "serve"
print(shadow_sampled("EPISODE_BOUNDARIES_MODE", "test-account", 5.0))
