# LIFECYCLE: permanent
"""Pinned candidate image and exact metadata schema; qualification and production admission remain external gates."""

READINESS_ENV = {
    'HOME': '/home/ubuntu',
    'PYTHONDONTWRITEBYTECODE': '1',
    'GIT_OPTIONAL_LOCKS': '0',
    'BATCH_JOBSTORE_MODE': 'firestore',
    'JOBSTORE_SHADOW_WRITES': 'off',
    'JOBSTORE_PRODUCTION_MIRROR': 'off',
    'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '0',
    'JOBSTORE_INDEX_READS': 'off',
}

CONTRACT = {
    'source_sha': '97074e78defa1a84b9d39c021e28aa70cf4f2e4e',
    'supervisor_sha256': '1b6a0a1ed5ca8dbc7f8087ae51441539a8aa9b4f4da2171932e2f08af9de699f',
    'image': 'gcr.io/based-hardware/jobstore-reconcile-operator@sha256:f713574047679618ecea32ff29b939f20fa3d63cfea33ba9cdf6643577d2c145',
    'qualification_run': None,
    'migrations': [
        [1, 'doc_mode_store', '4f121b4df8ffe9c8369cc5b920f94010d3ada94b11909c49318db9f49f6ba205'],
        [2, 'outbox', '6e53430b74b89c7a2e3b031faec7766f0374fed8aefa4e916fb19e27950d4e6e'],
        [3, 'outbox_wake_pending', '8b97c1aa851f9801fff6a214184d74f6606fc4a0613b1a1deb7117fec7d9d4b4'],
        [4, 'merge_and_projection_hints', 'b6ff0b0093c7ae8f89bc8bc30648048d03e5f07683c73ddc3bcd0d246cbd4500'],
        [5, 'byte_order_key_indexes', '650f78f15a49de950f05b6e3c361a9ebf257e36fdb1f7f58860cca2d7af32620'],
        [6, 'transactional_fresh_gate', '6e9baf9cd37300a3d134f9354df72786548efdd35b48f7b6f0a8833834660cdd'],
        [7, 'ready_owners', '9963c19a3d8c4c87578937c3b2b3cdf4635fc3211209e6a23b4a08f5ebb76cfa'],
        [8, 'allowance_holds', 'b89f731ff1f45ba0a9922e8cf0377a7b05054c76df74de9c67825f0606b6acdb'],
    ],
}
