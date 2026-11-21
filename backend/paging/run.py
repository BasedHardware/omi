"""Launch the pager with shared operations logging and bounded request concurrency."""

from gunicorn.app.base import BaseApplication

from omi_logging import configure_logging

from .app import OPS_PROJECT, production_app

configure_logging('omi-pager', project=OPS_PROJECT)


class PagerServer(BaseApplication):
    def load_config(self):
        self.cfg.set('bind', '0.0.0.0:8080')
        self.cfg.set('threads', 8)
        self.cfg.set('timeout', 55)

    def load(self):
        return production_app()


if __name__ == '__main__':
    PagerServer().run()
