"""Streaming artifact writes over the stack's generation-fenced local adapter."""

from utils.other.local_storage import LocalBlob, LocalBucket, LocalStorageClient, local_storage_root_from_env


class LifecycleBlob(LocalBlob):
    def upload_from_file(self, stream, *, content_type=None, if_generation_match=None, **kwargs):
        self.upload_from_string(
            stream.read(), content_type=content_type, if_generation_match=if_generation_match, **kwargs
        )


class LifecycleBucket(LocalBucket):
    def blob(self, name, generation=None):
        return LifecycleBlob(self, name, generation)


class LifecycleStorageClient(LocalStorageClient):
    def bucket(self, name):
        return LifecycleBucket(self.root, name)


def create_local_storage():
    root = local_storage_root_from_env()
    if root is None:
        raise RuntimeError('lifecycle artifacts require the isolated local storage adapter')
    return LifecycleStorageClient(root)
