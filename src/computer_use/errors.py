class ComputerUseError(Exception):
    """The desktop action could not be completed."""


class PolicyError(ComputerUseError):
    """The action is blocked by the opt-in policy or the kill switch."""
