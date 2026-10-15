"""Domain exceptions for OCR adapter failures."""


class OCRAdapterError(Exception):
    """Base class for expected OCR adapter failures."""


class OCRDependencyError(OCRAdapterError):
    """An OCR engine or its native runtime is unavailable."""


class OCRInputError(OCRAdapterError):
    """The supplied image bytes are empty, invalid, or exceed safe limits."""


class OCRExecutionError(OCRAdapterError):
    """The OCR engine failed to process an otherwise valid image."""
