class Friend:
    def __init__(self, device):
        self.id = device.address
        self.name = device.name