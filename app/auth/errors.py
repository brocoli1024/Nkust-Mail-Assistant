class AuthError(RuntimeError):
    """Only fixed error codes cross the network/crypto boundary."""


class ReauthorizationRequired(AuthError):
    pass
