from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from modal import Image, App, Secret, asgi_app, mount

# from _mem0 import router as mem0_router
from _multion import router as multion_router
# from advanced import openglass as advanced_openglass_router
from advanced import realtime as advanced_realtime_router
from basic import memory_created as basic_memory_created_router
from basic import realtime as basic_realtime_router
from oauth import memory_created as oauth_memory_created_router

app = FastAPI()
app.mount("/templates/static", StaticFiles(directory="templates/static"), name="templates_static")

modal_app = App(
    name='plugins_examples',
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
    memory=(1024, 2048),
    cpu=4,
    allow_concurrent_inputs=10,
)
@asgi_app()
def plugins_app():
    return app


app.include_router(basic_memory_created_router.router)
app.include_router(basic_realtime_router.router)

app.include_router(oauth_memory_created_router.router)

app.include_router(advanced_realtime_router.router)
# app.include_router(advanced_openglass_router.router)

# ***********************************************
# ************ EXTERNAL INTEGRATIONS ************
# ***********************************************


app.include_router(multion_router.router)
# app.include_router(mem0_router.router)
