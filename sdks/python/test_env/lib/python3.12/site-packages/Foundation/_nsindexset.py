import objc


def __len__(self):
    return self.length()


def __getitem__(self, idx):
    if isinstance(idx, slice):
        raise ValueError(idx)
    return self.indexAtPosition_(idx)


def __add__(self, value):
    return self.indexPathByAddingIndex_(value)


objc.addConvenienceForClass(
    "NSIndexPath",
    (("__len__", __len__), ("__getitem__", __getitem__), ("__add__", __add__)),
)
