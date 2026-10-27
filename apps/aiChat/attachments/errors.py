class AttachmentError(Exception):
    """
    An uploaded file was rejected or could not be processed.

    `code` is a key in `apps.aiChat.messages`; `params` fill its template.
    The message shown to the user is built from these, never from the
    underlying exception.
    """

    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code = code
        self.params = params
