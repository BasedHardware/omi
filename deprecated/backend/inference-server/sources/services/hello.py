from sources.service import Service

class HelloService(Service):
    def __init__(self):
        super().__init__("hello")

    def load(self):
        print("HelloService loaded")
        pass # No need to load anything

    def unload(self):
        print("HelloService unloaded")
        pass # No need to unload anything

    def execute(self, args):
        yield { "text": "Hello, " + args["name"] + "!" }
        yield { "text": "How are you today?" }
        yield { "text": "I'm doing great!" }
        yield { "text": "Goodbye!" }