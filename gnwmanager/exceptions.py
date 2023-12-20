class DebugProbeConnectionError(Exception):
    """Error connecting to debug probe."""


class DataError(Exception):
    """Some data was not as expected."""


class MissingThirdPartyError(Exception):
    """A required external library/executable is missing."""
