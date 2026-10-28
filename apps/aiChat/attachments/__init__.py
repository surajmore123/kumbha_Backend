"""
Uploaded chat files: detection, validation and preparation for the model.

Each modality lives in its own module so it can be tested on its own:
`detection` (what the file really is), `images`, `audio`, `documents`
and `storage` (where processed files and extracts are kept).
"""

from apps.aiChat.attachments.errors import AttachmentError

__all__ = ["AttachmentError"]
