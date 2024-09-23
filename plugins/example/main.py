from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from modal import App, mount
from modal import Image, Secret, asgi_app

# from _mem0 import router as mem0_router
from _multion import router as multion_router
from basic import memory_created as basic_memory_created_router
from oauth import memory_created as oauth_memory_created_router
from zapier import memory_created as zapier_memory_created_router

# from advanced import openglass as advanced_openglass_router

# ************* @DEPRECATED **************
# REALTIME plugins are not ready yet: (After various attempts, we found the following:
# 1. Super expensive to maintain, running a llm or certain logic every 3 seconds for 10 hours a day is not cheap.
# 2. There has to be a better way to trigger those plugins, current way is not efficient.
# 3. Didn't find killer use cases.
# from advanced import realtime as advanced_realtime_router
# from basic import realtime as basic_realtime_router
# ****************************************

app = FastAPI()
app.mount("/templates/static", StaticFiles(directory="templates/static"), name="templates_static")

modal_app = App(
    name='plugins',
    secrets=[Secret.from_dotenv('.env')],
    mounts=[mount.Mount.from_local_dir('templates/', remote_path='templates/')]
)


@modal_app.function(
    image=(
            Image.debian_slim()
            # .apt_install('libgl1-mesa-glx', 'libglib2.0-0')
            .pip_install_from_requirements('requirements.txt')
    ),
    keep_warm=1,  # need 7 for 1rps
    memory=(128, 256),
    cpu=1,
    allow_concurrent_inputs=10,
)
@asgi_app()
def api():
    return app


app.include_router(basic_memory_created_router.router)
app.include_router(oauth_memory_created_router.router)
app.include_router(zapier_memory_created_router.router)

# app.include_router(basic_realtime_router.router)
# app.include_router(advanced_realtime_router.router)
# app.include_router(advanced_openglass_router.router)

# ***********************************************
# ************ EXTERNAL INTEGRATIONS ************
# ***********************************************

# Multion
app.include_router(multion_router.router)
