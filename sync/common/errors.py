"""Common errors used by the SKEO Syncer."""


class Error(Exception):
    pass


class CommunicationError(Error):
    """Indicates that a communication failure with a system happened."""


class NotFoundError(Error):
    """Indicates that the product model is not found in a system."""


class MultipleResultsError(Error):
    """Indicates that the product model has multiple copies in a system."""


class UnhandledSystemError(Error):
    """Indicates ttrying to connect to an unhandled external system."""


class UnhandledTagError(Error):
    """Indicates that an XML tag is unhandled by the parser."""

class PlatformNotBehavingError(Error):
    """Indicates that the platform (usually Lazada) is lying or delayed."""