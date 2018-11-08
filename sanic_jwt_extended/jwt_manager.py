import datetime

from jwt import ExpiredSignatureError, InvalidTokenError
from sanic.response import HTTPResponse

from sanic_jwt_extended.config import config
from sanic_jwt_extended.exceptions import (
    JWTDecodeError, NoAuthorizationError, InvalidHeaderError, WrongTokenError,
    RevokedTokenError, FreshTokenRequired, CSRFError, UserLoadError,
    UserClaimsVerificationError
)
from sanic_jwt_extended.default_callbacks import (
    default_expired_token_callback, default_user_claims_callback,
    default_user_identity_callback, default_invalid_token_callback,
    default_unauthorized_callback, default_needs_fresh_token_callback,
    default_revoked_token_callback, default_user_loader_error_callback,
    default_claims_verification_callback, default_verify_claims_failed_callback,
    default_decode_key_callback, default_encode_key_callback
)
from sanic_jwt_extended.tokens import (
    encode_refresh_token, encode_access_token
)
from sanic_jwt_extended.utils import get_jwt_identity

# for type hints
from sanic import Sanic
from typing import Awaitable, Any, Callable


class JWTManager(object):
    """
    An object used to hold JWT settings and callback functions for the
    Flask-JWT-Extended extension.

    Instances of :class:`JWTManager` are *not* bound to specific apps, so
    you can create one in the main body of your code and then bind it
    to your app in a factory function.
    """
    _user_claims_callback: Callable[[Any], Awaitable[dict]]
    _user_identity_callback: Callable[[Any], Awaitable[Any]]
    _expired_token_callback: Callable[[], Awaitable[HTTPResponse]]
    _invalid_token_callback: Callable[[str], Awaitable[HTTPResponse]]
    _unauthorized_callback: Callable[[str], Awaitable[HTTPResponse]]
    _needs_fresh_token_callback: Callable[[], Awaitable[HTTPResponse]]
    _revoked_token_callback: Callable[[], Awaitable[HTTPResponse]]
    _user_loader_callback: Callable[..., Awaitable[Any]]
    _user_loader_error_callback: Callable[[str], Awaitable[HTTPResponse]]
    _token_in_blacklist_callback: Callable[..., Awaitable[bool]]
    _claims_verification_callback: Callable[..., Awaitable[bool]]
    _verify_claims_failed_callback: Callable[[], Awaitable[HTTPResponse]]
    _decode_key_callback: Callable[[str], Awaitable[str]]
    _encode_key_callback: Callable[[str], Awaitable[str]]

    def __init__(self, app: Sanic=None):
        """
        Create the JWTManager instance. You can either pass a flask application
        in directly here to register this extension with the flask app, or
        call init_app after creating this object (in a factory pattern).

        :param app: A Sanic application
        """
        # Register the default error handler callback methods. These can be
        # overridden with the appropriate loader decorators
        self._user_claims_callback = default_user_claims_callback
        self._user_identity_callback = default_user_identity_callback
        self._expired_token_callback = default_expired_token_callback
        self._invalid_token_callback = default_invalid_token_callback
        self._unauthorized_callback = default_unauthorized_callback
        self._needs_fresh_token_callback = default_needs_fresh_token_callback
        self._revoked_token_callback = default_revoked_token_callback
        self._user_loader_callback = None
        self._user_loader_error_callback = default_user_loader_error_callback
        self._token_in_blacklist_callback = None
        self._claims_verification_callback = default_claims_verification_callback
        self._verify_claims_failed_callback = default_verify_claims_failed_callback
        self._decode_key_callback = default_decode_key_callback
        self._encode_key_callback = default_encode_key_callback

        # Register this extension with the flask app now (if it is provided)
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Sanic):
        """
        Register this extension with the flask app.

        :param app: A Sanic application
        """

        # Set all the default configurations for this extension
        self._set_default_configuration_options(app)
        self._set_exception_callbacks(app)

    def _set_exception_callbacks(self, app: Sanic):
        """
        Sets the error handler callbacks used by this extension
        """
        @app.exception(NoAuthorizationError)
        async def handle_auth_error(e):
            return await self._unauthorized_callback(str(e))

        @app.exception(CSRFError)
        async def handle_csrf_error(e):
            return await self._unauthorized_callback(str(e))

        @app.exception(ExpiredSignatureError)
        async def handle_expired_error(e):
            return await self._expired_token_callback()

        @app.exception(InvalidHeaderError)
        async def handle_invalid_header_error(e):
            return await self._invalid_token_callback(str(e))

        @app.exception(InvalidTokenError)
        async def handle_invalid_token_error(e):
            return await self._invalid_token_callback(str(e))

        @app.exception(JWTDecodeError)
        async def handle_jwt_decode_error(e):
            return await self._invalid_token_callback(str(e))

        @app.exception(WrongTokenError)
        async def handle_wrong_token_error(e):
            return await self._invalid_token_callback(str(e))

        @app.exception(RevokedTokenError)
        async def handle_revoked_token_error(e):
            return await self._revoked_token_callback()

        @app.exception(FreshTokenRequired)
        async def handle_fresh_token_required(e):
            return await self._needs_fresh_token_callback()

        @app.exception(UserLoadError)
        async def handler_user_load_error(e):
            # The identity is already saved before this exception was raised,
            # otherwise a different exception would be raised, which is why we
            # can safely call get_jwt_identity() here
            identity: str = get_jwt_identity()
            return await self._user_loader_error_callback(identity)

        @app.exception(UserClaimsVerificationError)
        async def handle_failed_user_claims_verification(e):
            return await self._verify_claims_failed_callback()

    @staticmethod
    async def _set_default_configuration_options(app: Sanic):
        """
        Sets the default configuration options used by this extension
        """
        # Where to look for the JWT. Available options are cookies or headers
        app.config.setdefault('JWT_TOKEN_LOCATION', ['headers'])

        # Options for JWTs when the TOKEN_LOCATION is headers
        app.config.setdefault('JWT_HEADER_NAME', 'Authorization')
        app.config.setdefault('JWT_HEADER_TYPE', 'Bearer')

        # Options for JWTs then the TOKEN_LOCATION is query_string
        app.config.setdefault('JWT_QUERY_STRING_NAME', 'jwt')

        # Option for JWTs when the TOKEN_LOCATION is cookies
        app.config.setdefault('JWT_ACCESS_COOKIE_NAME', 'access_token_cookie')
        app.config.setdefault('JWT_REFRESH_COOKIE_NAME', 'refresh_token_cookie')
        app.config.setdefault('JWT_ACCESS_COOKIE_PATH', '/')
        app.config.setdefault('JWT_REFRESH_COOKIE_PATH', '/')
        app.config.setdefault('JWT_COOKIE_SECURE', False)
        app.config.setdefault('JWT_COOKIE_DOMAIN', None)
        app.config.setdefault('JWT_SESSION_COOKIE', True)
        app.config.setdefault('JWT_COOKIE_SAMESITE', None)

        # Option for JWTs when the TOKEN_LOCATION is json
        app.config.setdefault('JWT_JSON_KEY', 'access_token')
        app.config.setdefault('JWT_REFRESH_JSON_KEY', 'refresh_token')

        # Options for using double submit csrf protection
        app.config.setdefault('JWT_COOKIE_CSRF_PROTECT', True)
        app.config.setdefault('JWT_CSRF_METHODS', ['POST', 'PUT', 'PATCH', 'DELETE'])
        app.config.setdefault('JWT_ACCESS_CSRF_HEADER_NAME', 'X-CSRF-TOKEN')
        app.config.setdefault('JWT_REFRESH_CSRF_HEADER_NAME', 'X-CSRF-TOKEN')
        app.config.setdefault('JWT_CSRF_IN_COOKIES', True)
        app.config.setdefault('JWT_ACCESS_CSRF_COOKIE_NAME', 'csrf_access_token')
        app.config.setdefault('JWT_REFRESH_CSRF_COOKIE_NAME', 'csrf_refresh_token')
        app.config.setdefault('JWT_ACCESS_CSRF_COOKIE_PATH', '/')
        app.config.setdefault('JWT_REFRESH_CSRF_COOKIE_PATH', '/')

        # How long an a token will live before they expire.
        app.config.setdefault('JWT_ACCESS_TOKEN_EXPIRES', datetime.timedelta(minutes=15))
        app.config.setdefault('JWT_REFRESH_TOKEN_EXPIRES', datetime.timedelta(days=30))

        # What algorithm to use to sign the token. See here for a list of options:
        # https://github.com/jpadilla/pyjwt/blob/master/jwt/api_jwt.py
        app.config.setdefault('JWT_ALGORITHM', 'HS256')

        # Secret key to sign JWTs with. Only used if a symmetric algorithm is
        # used (such as the HS* algorithms). We will use the app secret key
        # if this is not set.
        app.config.setdefault('JWT_SECRET_KEY', None)

        # Keys to sign JWTs with when use when using an asymmetric
        # (public/private key) algorithm, such as RS* or EC*
        app.config.setdefault('JWT_PRIVATE_KEY', None)
        app.config.setdefault('JWT_PUBLIC_KEY', None)

        # Options for blacklisting/revoking tokens
        app.config.setdefault('JWT_BLACKLIST_ENABLED', False)
        app.config.setdefault('JWT_BLACKLIST_TOKEN_CHECKS', ['access', 'refresh'])

        app.config.setdefault('JWT_IDENTITY_CLAIM', 'identity')
        app.config.setdefault('JWT_USER_CLAIMS', 'user_claims')

        app.config.setdefault('JWT_CLAIMS_IN_REFRESH_TOKEN', False)

        app.config.setdefault('JWT_ERROR_MESSAGE_KEY', 'msg')

    async def user_claims_loader(self, callback: Callable[[Any], Awaitable[dict]]):
        """
        This decorator sets the callback function for adding custom claims to an
        access token when :func:`~sanic_jwt_extended.create_access_token` is
        called. By default, no extra user claims will be added to the JWT.

        *HINT*: The callback function must be a function that takes only **one** argument,
        which is the object passed into
        :func:`~sanic_jwt_extended.create_access_token`, and returns the custom
        claims you want included in the access tokens. This returned claims
        must be *JSON serializable*.
        """
        self._user_claims_callback = callback
        return callback

    async def user_identity_loader(self, callback: Callable[[Any], Awaitable[Any]]):
        """
        This decorator sets the callback function for getting the JSON
        serializable identity out of whatever object is passed into
        :func:`~sanic_jwt_extended.create_access_token` and
        :func:`~sanic_jwt_extended.create_refresh_token`. By default, this will
        return the unmodified object that is passed in as the `identity` kwarg
        to the above functions.

        *HINT*: The callback function must be a function that takes only **one** argument,
        which is the object passed into
        :func:`~sanic_jwt_extended.create_access_token` or
        :func:`~sanic_jwt_extended.create_refresh_token`, and returns the
        *JSON serializable* identity of this token.
        """
        self._user_identity_callback = callback
        return callback

    async def expired_token_loader(self, callback: Callable[[], Awaitable[HTTPResponse]]):
        """
        This decorator sets the callback function that will be called if an
        expired JWT attempts to access a protected endpoint. The default
        implementation will return a 401 status code with the JSON:

        {"msg": "Token has expired"}

        *HINT*: The callback must be a function that takes **zero** arguments, and returns
        a *Flask response*.
        """
        self._expired_token_callback = callback
        return callback

    def invalid_token_loader(self, callback: Callable[[str], Awaitable[HTTPResponse]]):
        """
        This decorator sets the callback function that will be called if an
        invalid JWT attempts to access a protected endpoint. The default
        implementation will return a 422 status code with the JSON:

        {"msg": "<error description>"}

        *HINT*: The callback must be a function that takes only **one** argument, which is
        a string which contains the reason why a token is invalid, and returns
        a *Flask response*.
        """
        self._invalid_token_callback = callback
        return callback

    def unauthorized_loader(self, callback: Callable[[str], Awaitable[HTTPResponse]]):
        """
        This decorator sets the callback function that will be called if an
        no JWT can be found when attempting to access a protected endpoint.
        The default implementation will return a 401 status code with the JSON:

        {"msg": "<error description>"}

        *HINT*: The callback must be a function that takes only **one** argument, which is
        a string which contains the reason why a JWT could not be found, and
        returns a *Flask response*.
        """
        self._unauthorized_callback = callback
        return callback

    def needs_fresh_token_loader(self, callback: Callable[[], Awaitable[HTTPResponse]]):
        """
        This decorator sets the callback function that will be called if a
        valid and non-fresh token attempts to access an endpoint protected with
        the :func:`~sanic_jwt_extended.fresh_jwt_required` decorator. The
        default implementation will return a 401 status code with the JSON:

        {"msg": "Fresh token required"}

        *HINT*: The callback must be a function that takes **no** arguments, and returns
        a *Flask response*.
        """
        self._needs_fresh_token_callback = callback
        return callback

    def revoked_token_loader(self, callback: Callable[[], Awaitable[HTTPResponse]]):
        """
        This decorator sets the callback function that will be called if a
        revoked token attempts to access a protected endpoint. The default
        implementation will return a 401 status code with the JSON:

        {"msg": "Token has been revoked"}

        *HINT*: The callback must be a function that takes **no** arguments, and returns
        a *Flask response*.
        """
        self._revoked_token_callback = callback
        return callback

    def user_loader_callback_loader(self, callback: Callable[..., Awaitable[Any]]):
        """
        This decorator sets the callback function that will be called to
        automatically load an object when a protected endpoint is accessed.
        By default this is not used.

        *HINT*: The callback must take **one** argument which is the identity JWT
        accessing the protected endpoint, and it must return any object (which can
        then be accessed via the :attr:`~sanic_jwt_extended.current_user` LocalProxy
        in the protected endpoint), or `None` in the case of a user not being
        able to be loaded for any reason. If this callback function returns
        `None`, the :meth:`~sanic_jwt_extended.JWTManager.user_loader_error_loader`
        will be called.
        """
        self._user_loader_callback = callback
        return callback

    def user_loader_error_loader(self, callback: Callable[[str], Awaitable[HTTPResponse]]):
        """
        This decorator sets the callback function that will be called if `None`
        is returned from the
        :meth:`~sanic_jwt_extended.JWTManager.user_loader_callback_loader`
        callback function. The default implementation will return
        a 401 status code with the JSON:

        {"msg": "Error loading the user <identity>"}

        *HINT*: The callback must be a function that takes **one** argument, which is the
        identity of the user who failed to load, and must return a *Flask response*.
        """
        self._user_loader_error_callback = callback
        return callback

    def token_in_blacklist_loader(self, callback: Callable[..., Awaitable[bool]]):
        """
        This decorator sets the callback function that will be called when
        a protected endpoint is accessed and will check if the JWT has been
        been revoked. By default, this callback is not used.

        *HINT*: The callback must be a function that takes **one** argument, which is the
        decoded JWT (python dictionary), and returns *`True`* if the token
        has been blacklisted (or is otherwise considered revoked), or *`False`*
        otherwise.
        """
        self._token_in_blacklist_callback = callback
        return callback

    def claims_verification_loader(self, callback: Callable[..., Awaitable[bool]]):
        """
        This decorator sets the callback function that will be called when
        a protected endpoint is accessed, and will check if the custom claims
        in the JWT are valid. By default, this callback is not used. The
        error returned if the claims are invalid can be controlled via the
        :meth:`~sanic_jwt_extended.JWTManager.claims_verification_failed_loader`
        decorator.

        *HINT*: This callback must be a function that takes **one** argument, which is the
        custom claims (python dict) present in the JWT, and returns *`True`* if the
        claims are valid, or *`False`* otherwise.
        """
        self._claims_verification_callback = callback
        return callback

    def claims_verification_failed_loader(self, callback: Callable[[], Awaitable[HTTPResponse]]):
        """
        This decorator sets the callback function that will be called if
        the :meth:`~sanic_jwt_extended.JWTManager.claims_verification_loader`
        callback returns False, indicating that the user claims are not valid.
        The default implementation will return a 400 status code with the JSON:

        {"msg": "User claims verification failed"}

        *HINT*: This callback must be a function that takes **no** arguments, and returns
        a *Flask response*.
        """
        self._verify_claims_failed_callback = callback
        return callback

    def decode_key_loader(self, callback: Callable[[str], Awaitable[str]]):
        """
        This decorator sets the callback function for getting the JWT decode key and
        can be used to dynamically choose the appropriate decode key based on token
        contents.

        The default implementation returns the decode key specified by
        `JWT_SECRET_KEY` or `JWT_PUBLIC_KEY`, depending on the signing algorithm.

        *HINT*: The callback function must be a function that takes only **one** argument,
        which is the unverified claims of the jwt (dictionary) and must return a *string*
        which is the decode key to verify the token.
        """
        self._decode_key_callback = callback
        return callback

    def encode_key_loader(self, callback: Callable[[str], Awaitable[str]]):
        """
        This decorator sets the callback function for getting the JWT encode key and
        can be used to dynamically choose the appropriate encode key based on the
        token identity.

        The default implementation returns the encode key specified by
        `JWT_SECRET_KEY` or `JWT_PRIVATE_KEY`, depending on the signing algorithm.

        *HINT*: The callback function must be a function that takes only **one**
        argument, which is the identity as passed into the create_access_token
        or create_refresh_token functions, and must return a *string* which is
        the decode key to verify the token.
        """
        self._encode_key_callback = callback
        return callback

    def _create_refresh_token(self, identity: Any, expires_delta: datetime.timedelta =None) -> str:
        if expires_delta is None:
            expires_delta = config.refresh_expires

        if config.user_claims_in_refresh_token:
            user_claims: Awaitable[dict] = self._user_claims_callback(identity)
        else:
            user_claims = None

        refresh_token: str = encode_refresh_token(
            identity=self._user_identity_callback(identity),
            secret=self._encode_key_callback(identity),
            algorithm=config.algorithm,
            expires_delta=expires_delta,
            user_claims=user_claims,
            csrf=config.csrf_protect,
            identity_claim_key=config.identity_claim_key,
            user_claims_key=config.user_claims_key,
            json_encoder=config.json_encoder
        )
        return refresh_token

    def _create_access_token(self, identity: Any, fresh: bool=False, expires_delta: datetime.timedelta=None) -> str:
        if expires_delta is None:
            expires_delta = config.access_expires

        access_token: str = encode_access_token(
            identity=self._user_identity_callback(identity),
            secret=self._encode_key_callback(identity),
            algorithm=config.algorithm,
            expires_delta=expires_delta,
            fresh=fresh,
            user_claims=self._user_claims_callback(identity),
            csrf=config.csrf_protect,
            identity_claim_key=config.identity_claim_key,
            user_claims_key=config.user_claims_key,
            json_encoder=config.json_encoder
        )
        return access_token