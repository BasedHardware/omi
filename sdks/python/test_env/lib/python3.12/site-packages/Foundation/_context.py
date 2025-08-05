import Foundation


class NSDisabledAutomaticTermination:
    def __init__(self, reason):
        self._reason = reason
        self._info = Foundation.NSProcessInfo.processInfo()

    def __enter__(self):
        self._info.disableAutomaticTermination_(self._reason)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._info.enableAutomaticTermination_(self._reason)
        return False


class NSDisabledSuddenTermination:
    def __init__(self):
        self._info = Foundation.NSProcessInfo.processInfo()

    def __enter__(self):
        self._info.disableSuddenTermination()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._info.enableSuddenTermination()
        return False
