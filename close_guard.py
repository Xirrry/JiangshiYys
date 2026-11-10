"""Defer close decisions so the native UI thread stays free for the web dialog."""
class CloseGuard:
    def __init__(self, allowed, schedule, request):
        self.allowed, self.schedule, self.request = allowed, schedule, request
        self.pending = False

    def __call__(self):
        if self.allowed():
            return True
        if not self.pending:
            self.pending = True
            self.schedule(self._request)
        return False

    def _request(self):
        try:
            self.request()
        finally:
            self.pending = False
