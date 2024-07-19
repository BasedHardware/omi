from .services.hello import HelloService
from .services.whisper import WhisperService
from .services.whisperx import WhisperXService
from .services.enhance import EnhanceService

def load_services():
    services = []

    # Register all services here
    print("Loading services...")
    services.append(HelloService())
    services.append(WhisperService())
    services.append(EnhanceService())
    services.append(WhisperXService())
    services.append(SileroVADService())

    # Preload services
    for service in services:
        service.preload()

    return services