class DataError(Exception):
    """Some data was not as expected."""


class MissingThirdPartyError(Exception):
    """A required external library/executable is missing."""
