class Service:

    def __init__(self, name):
        self.name = name
        
    def load(self):
        raise NotImplementedError

    def unload(self):
        raise NotImplementedError

    def preload(self):
        pass # Optional

    def execute(self, args):
        raise NotImplementedError