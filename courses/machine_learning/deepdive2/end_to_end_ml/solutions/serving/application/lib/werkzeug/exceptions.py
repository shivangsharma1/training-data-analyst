# -*- coding: utf-8 -*-
"""
    werkzeug.exceptions
    ~~~~~~~~~~~~~~~~~~~

    This module implements a number of Python exceptions you can raise from
    within your views to trigger a standard non-200 response.


    Usage Example
    -------------

    ::

        from werkzeug.wrappers import BaseRequest
        from werkzeug.wsgi import responder
        from werkzeug.exceptions import HTTPException, NotFound

        def view(request):
            raise NotFound()

        @responder
        def application(environ, start_response):
            request = BaseRequest(environ)
            try:
                return view(request)
            except HTTPException as e:
                return e


    As you can see from this example those exceptions are callable WSGI
    applications.  Because of Python 2.4 compatibility those do not extend
    from the response objects but only from the python exception class.

    As a matter of fact they are not Werkzeug response objects.  However you
    can get a response object by calling ``get_response()`` on a HTTP
    exception.

    Keep in mind that you have to pass an environment to ``get_response()``
    because some errors fetch additional information from the WSGI
    environment.

    If you want to hook in a different exception page to say, a 404 status
    code, you can add a second except for a specific subclass of an error::

        @responder
        def application(environ, start_response):
            request = BaseRequest(environ)
            try:
                return view(request)
            except NotFound, e:
                return not_found(request)
            except HTTPException, e:
                return e


    :copyright: 2007 Pallets
    :license: BSD-3-Clause
"""
import sys

from ._compat import implements_to_string
from ._compat import integer_types
from ._compat import iteritems
from ._compat import text_type
from ._internal import _get_environ
from .utils import escape


@implements_to_string
class HTTPException(Exception):
    """Baseclass for all HTTP exceptions.  This exception can be called as WSGI
    application to render a default error page or you can catch the subclasses
    of it independently and render nicer error messages.
    """

    code = None
    description = None

    def __init__(self, description=None, response=None):
        super(HTTPException, self).__init__()
        if description is not None:
            self.description = description
        self.response = response

    @classmethod
    def wrap(cls, exception, name=None):
        """Create an exception that is a subclass of the calling HTTP
        exception and the ``exception`` argument.

        The first argument to the class will be passed to the
        wrapped ``exception``, the rest to the HTTP exception. If
        ``e.args`` is not empty and ``e.show_exception`` is ``True``,
        the wrapped exception message is added to the HTTP error
        description.

        .. versionchanged:: 0.15.5
            The ``show_exception`` attribute controls whether the
            description includes the wrapped exception message.

        .. versionchanged:: 0.15.0
            The description includes the wrapped exception message.
        """

        class newcls(cls, exception):
            _description = cls.description
            show_exception = False

            def __init__(self, arg=None, *args, **kwargs):
                super(cls, self).__init__(*args, **kwargs)

                if arg is None:
                    exception.__init__(self)
                else:
                    exception.__init__(self, arg)

            @property
            def description(self):
                if self.show_exception:
                    return "{}\n{}: {}".format(
                        self._description, exception.__name__, exception.__str__(self)
                    )

                return self._description

            @description.setter
            def description(self, value):
                self._description = value

        newcls.__module__ = sys._getframe(1).f_globals.get("__name__")
        name = name or cls.__name__ + exception.__name__
        newcls.__name__ = newcls.__qualname__ = name
        return newcls

    @property
    def name(self):
        """The status name."""
        from .http import HTTP_STATUS_CODES

        return HTTP_STATUS_CODES.get(self.code, "Unknown Error")

    def get_description(self, environ=None):
        """Get the description."""
        return u"<p>%s</p>" % escape(self.description).replace("\n", "<br>")

    def get_body(self, environ=None):
        """Get the HTML body."""
        return text_type(
            (
                u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
                u"<title>%(code)s %(name)s</title>\n"
                u"<h1>%(name)s</h1>\n"
                u"%(description)s\n"
            )
            % {
                "code": self.code,
                "name": escape(self.name),
                "description": self.get_description(environ),
            }
        )

    def get_headers(self, environ=None):
        """Get a list of headers."""
        return [("Content-Type", "text/html")]

    def get_response(self, environ=None):
        """Get a response object.  If one was passed to the exception
        it's returned directly.

        :param environ: the optional environ for the request.  This
                        can be used to modify the response depending
                        on how the request looked like.
        :return: a :class:`Response` object or a subclass thereof.
        """
        from .wrappers.response import Response

        if self.response is not None:
            return self.response
        if environ is not None:
            environ = _get_environ(environ)
        headers = self.get_headers(environ)
        return Response(self.get_body(environ), self.code, headers)

    def __call__(self, environ, start_response):
        """Call the exception as WSGI application.

        :param environ: the WSGI environment.
        :param start_response: the response callable provided by the WSGI
                               server.
        """
        response = self.get_response(environ)
        return response(environ, start_response)

    def __str__(self):
        code = self.code if self.code is not None else "???"
        return "%s %s: %s" % (code, self.name, self.description)

    def __repr__(self):
        code = self.code if self.code is not None else "???"
        return "<%s '%s: %s'>" % (self.__class__.__name__, code, self.name)


class BadRequest(HTTPException):
    """*400* `Bad Request`

    Raise if the browser sends something to the application the application
    or server cannot handle.
    """

    code = 400
    description = (
        "The browser (or proxy) sent a request that this server could "
        "not understand."
    )


class ClientDisconnected(BadRequest):
    """Internal exception that is raised if Werkzeug detects a disconnected
    client.  Since the client is already gone at that point attempting to
    send the error message to the client might not work and might ultimately
    result in another exception in the server.  Mainly this is here so that
    it is silenced by default as far as Werkzeug is concerned.

    Since disconnections cannot be reliably detected and are unspecified
    by WSGI to a large extent this might or might not be raised if a client
    is gone.

    .. versionadded:: 0.8
    """


class SecurityError(BadRequest):
    """Raised if something triggers a security error.  This is otherwise
    exactly like a bad request error.

    .. versionadded:: 0.9
    """


class BadHost(BadRequest):
    """Raised if the submitted host is badly formatted.

    .. versionadded:: 0.11.2
    """


class Unauthorized(HTTPException):
    """*401* ``Unauthorized``

    Raise if the user is not authorized to access a resource.

    The ``www_authenticate`` argument should be used to set the
    ``WWW-Authenticate`` header. This is used for HTTP basic auth and
    other schemes. Use :class:`~werkzeug.datastructures.WWWAuthenticate`
    to create correctly formatted values. Strictly speaking a 401
    response is invalid if it doesn't provide at least one value for
    this header, although real clients typically don't care.

    :param description: Override the default message used for the body
        of the response.
    :param www-authenticate: A single value, or list of values, for the
        WWW-Authenticate header.

    .. versionchanged:: 0.15.3
        If the ``www_authenticate`` argument is not set, the
        ``WWW-Authenticate`` header is not set.

    .. versionchanged:: 0.15.3
        The ``response`` argument was restored.

    .. versionchanged:: 0.15.1
        ``description`` was moved back as the first argument, restoring
         its previous position.

    .. versionchanged:: 0.15.0
        ``www_authenticate`` was added as the first argument, ahead of
        ``description``.
    """

    code = 401
    description = (
        "The server could not verify that you are authorized to access"
        " the URL requested. You either supplied the wrong credentials"
        " (e.g. a bad password), or your browser doesn't understand"
        " how to supply the credentials required."
    )

    def __init__(self, description=None, response=None, www_authenticate=None):
        HTTPException.__init__(self, description, response)

        if www_authenticate is not None:
            if not isinstance(www_authenticate, (tuple, list)):
                www_authenticate = (www_authenticate,)

        self.www_authenticate = www_authenticate

    def get_headers(self, environ=None):
        headers = HTTPException.get_headers(self, environ)
        if self.www_authenticate:
            headers.append(
                ("WWW-Authenticate", ", ".join([str(x) for x in self.www_authenticate]))
            )
        return headers


class Forbidden(HTTPException):
    """*403* `Forbidden`

    Raise if the user doesn't have the permission for the requested resource
    but was authenticated.
    """

    code = 403
    description = (
        "You don't have the permission to access the requested"
        " resource. It is either read-protected or not readable by the"
        " server."
    )


class NotFound(HTTPException):
    """*404* `Not Found`

    Raise if a resource does not exist and never existed.
    """

    code = 404
    description = (
        "The requested URL was not found on the server. If you entered"
        " the URL manually please check your spelling and try again."
    )


class MethodNotAllowed(HTTPException):
    """*405* `Method Not Allowed`

    Raise if the server used a method the resource does not handle.  For
    example `POST` if the resource is view only.  Especially useful for REST.

    The first argument for this exception should be a list of allowed methods.
    Strictly speaking the response would be invalid if you don't provide valid
    methods in the header which you can do with that list.
    """

    code = 405
    description = "The method is not allowed for the requested URL."

    def __init__(self, valid_methods=None, description=None):
        """Takes an optional list of valid http methods
        starting with werkzeug 0.3 the list will be mandatory."""
        HTTPException.__init__(self, description)
        self.valid_methods = valid_methods

    def get_headers(self, environ=None):
        headers = HTTPException.get_headers(self, environ)
        if self.valid_methods:
            headers.append(("Allow", ", ".join(self.valid_methods)))
        return headers


class NotAcceptable(HTTPException):
    """*406* `Not Acceptable`

    Raise if the server can't return any content conforming to the
    `Accept` headers of the client.
    """

    code = 406

    description = (
        "The resource identified by the request is only capable of"
        " generating response entities which have content"
        " characteristics not acceptable according to the accept"
        " headers sent in the request."
    )


class RequestTimeout(HTTPException):
    """*408* `Request Timeout`

    Raise to signalize a timeout.
    """

    code = 408
    description = (
        "The server closed the network connection because the browser"
        " didn't finish the request within the specified time."
    )


class Conflict(HTTPException):
    """*409* `Conflict`

    Raise to signal that a request cannot be completed because it conflicts
    with the current state on the server.

    .. versionadded:: 0.7
    """

    code = 409
    description = (
        "A conflict happened while processing the request. The"
        " resource might have been modified while the request was being"
        " processed."
    )


class Gone(HTTPException):
    """*410* `Gone`

    Raise if a resource existed previously and went away without new location.
    """

    code = 410
    description = (
        "The requested URL is no longer available on this server and"
        " there is no forwarding address. If you followed a link from a"
        " foreign page, please contact the author of this page."
    )


class LengthRequired(HTTPException):
    """*411* `Length Required`

    Raise if the browser submitted data but no ``Content-Length`` header which
    is required for the kind of processing the server does.
    """

    code = 411
    description = (
        "A request with this method requires a valid <code>Content-"
        "Length</code> header."
    )


class PreconditionFailed(HTTPException):
    """*412* `Precondition Failed`

    Status code used in combination with ``If-Match``, ``If-None-Match``, or
    ``If-Unmodified-Since``.
    """

    code = 412
    description = (
        "The precondition on the request for the URL failed positive evaluation."
    )


class RequestEntityTooLarge(HTTPException):
    """*413* `Request Entity Too Large`

    The status code one should return if the data submitted exceeded a given
    limit.
    """

    code = 413
    description = "The data value transmitted exceeds the capacity limit."


class RequestURITooLarge(HTTPException):
    """*414* `Request URI Too Large`

    Like *413* but for too long URLs.
    """

    code = 414
    description = (
        "The length of the requested URL exceeds the capacity limit for"
        " this server. The request cannot be processed."
    )


class UnsupportedMediaType(HTTPException):
    """*415* `Unsupported Media Type`

    The status code returned if the server is unable to handle the media type
    the client transmitted.
    """

    code = 415
    description = (
        "The server does not support the media type transmitted in the request."
    )


class RequestedRangeNotSatisfiable(HTTPException):
    """*416* `Requested Range Not Satisfiable`

    The client asked for an invalid part of the file.

    .. versionadded:: 0.7
    """

    code = 416
    description = "The server cannot provide the requested range."

    def __init__(self, length=None, units="bytes", description=None):
        """Takes an optional `Content-Range` header value based on ``length``
        parameter.
        """
        HTTPException.__init__(self, description)
        self.length = length
        self.units = units

    def get_headers(self, environ=None):
        headers = HTTPException.get_headers(self, environ)
        if self.length is not None:
            headers.append(("Content-Range", "%s */%d" % (self.units, self.length)))
        return headers


class ExpectationFailed(HTTPException):
    """*417* `Expectation Failed`

    The server cannot meet the requirements of the Expect request-header.

    .. versionadded:: 0.7
    """

    code = 417
    description = "The server could not meet the requirements of the Expect header"


class ImATeapot(HTTPException):
    """*418* `I'm a teapot`

    The server should return this if it is a teapot and someone attempted
    to brew coffee with it.

    .. versionadded:: 0.7
    """

    code = 418
    description = "This server is a teapot, not a coffee machine"


class UnprocessableEntity(HTTPException):
    """*422* `Unprocessable Entity`

    Used if the request is well formed, but the instructions are otherwise
    incorrect.
    """

    code = 422
    description = (
        "The request was well-formed but was unable to be followed due"
        " to semantic errors."
    )


class Locked(HTTPException):
    """*423* `Locked`

    Used if the resource that is being accessed is locked.
    """

    code = 423
    description = "The resource that is being accessed is locked."


class FailedDependency(HTTPException):
    """*424* `Failed Dependency`

    Used if the method could not be performed on the resource
    because the requested action depended on another action and that action failed.
    """

    code = 424
    description = (
        "The method could not be performed on the resource because the"
        " requested action depended on another action and that action"
        " failed."
    )


class PreconditionRequired(HTTPException):
    """*428* `Precondition Required`

    The server requires this request to be conditional, typically to prevent
    the lost update problem, which is a race condition between two or more
    clients attempting to update a resource through PUT or DELETE. By requiring
    each client to include a conditional header ("If-Match" or "If-Unmodified-
    Since") with the proper value retained from a recent GET request, the
    server ensures that each client has at least seen the previous revision of
    the resource.
    """

    code = 428
    description = (
        "This request is required to be conditional; try using"
        ' "If-Match" or "If-Unmodified-Since".'
    )


class TooManyRequests(HTTPException):
    """*429* `Too Many Requests`

    The server is limiting the rate at which this user receives responses, and
    this request exceeds that rate. (The server may use any convenient method
    to identify users and their request rates). The server may include a
    "Retry-After" header to indicate how long the user should wait before
    retrying.
    """

    code = 429
    description = "This user has exceeded an allotted request count. Try again later."


class RequestHeaderFieldsTooLarge(HTTPException):
    """*431* `Request Header Fields Too Large`

    The server refuses to process the request because the header fields are too
    large. One or more individual fields may be too large, or the set of all
    headers is too large.
    """

    code = 431
    description = "One or more header fields exceeds the maximum size."


class UnavailableForLegalReasons(HTTPException):
    """*451* `Unavailable For Legal Reasons`

    This status code indicates that the server is denying access to the
    resource as a consequence of a legal demand.
    """

    code = 451
    description = "Unavailable for legal reasons."


class InternalServerError(HTTPException):
    """*500* `Internal Server Error`

    Raise if an internal server error occurred.  This is a good fallback if an
    unknown error occurred in the dispatcher.
    """

    code = 500
    description = (
        "The server encountered an internal error and was unable to"
        " complete your request. Either the server is overloaded or"
        " there is an error in the application."
    )


class NotImplemented(HTTPException):
    """*501* `Not Implemented`

    Raise if the application does not support the action requested by the
    browser.
    """

    code = 501
    description = "The server does not support the action requested by the browser."


class BadGateway(HTTPException):
    """*502* `Bad Gateway`

    If you do proxying in your application you should return this status code
    if you received an invalid response from the upstream server it accessed
    in attempting to fulfill the request.
    """

    code = 502
    description = (
        "The proxy server received an invalid response from an upstream server."
    )


class ServiceUnavailable(HTTPException):
    """*503* `Service Unavailable`

    Status code you should return if a service is temporarily unavailable.
    """

    code = 503
    description = (
        "The server is temporarily unable to service your request due"
        " to maintenance downtime or capacity problems. Please try"
        " again later."
    )


class GatewayTimeout(HTTPException):
    """*504* `Gateway Timeout`

    Status code you should return if a connection to an upstream server
    times out.
    """

    code = 504
    description = "The connection to an upstream server timed out."


class HTTPVersionNotSupported(HTTPException):
    """*505* `HTTP Version Not Supported`

    The server does not support the HTTP protocol version used in the request.
    """

    code = 505
    description = (
        "The server does not support the HTTP protocol version used in the request."
    )


default_exceptions = {}
__all__ = ["HTTPException"]


def _find_exceptions():
    for _name, obj in iteritems(globals()):
        try:
            is_http_exception = issubclass(obj, HTTPException)
        except TypeError:
            is_http_exception = False
        if not is_http_exception or obj.code is None:
            continue
        __all__.append(obj.__name__)
        old_obj = default_exceptions.get(obj.code, None)
        if old_obj is not None and issubclass(obj, old_obj):
            continue
        default_exceptions[obj.code] = obj


_find_exceptions()
del _find_exceptions


class Aborter(object):
    """When passed a dict of code -> exception items it can be used as
    callable that raises exceptions.  If the first argument to the
    callable is an integer it will be looked up in the mapping, if it's
    a WSGI application it will be raised in a proxy exception.

    The rest of the arguments are forwarded to the exception constructor.
    """

    def __init__(self, mapping=None, extra=None):
        if mapping is None:
            mapping = default_exceptions
        self.mapping = dict(mapping)
        if extra is not None:
            self.mapping.update(extra)

    def __call__(self, code, *args, **kwargs):
        if not args and not kwargs and not isinstance(code, integer_types):
            raise HTTPException(response=code)
        if code not in self.mapping:
            raise LookupError("no exception for %r" % code)
        raise self.mapping[code](*args, **kwargs)


def abort(status, *args, **kwargs):
    """Raises an :py:exc:`HTTPException` for the given status code or WSGI
    application::

        abort(404)  # 404 Not Found
        abort(Response('Hello World'))

    Can be passed a WSGI application or a status code.  If a status code is
    given it's looked up in the list of exceptions and will raise that
    exception, if passed a WSGI application it will wrap it in a proxy WSGI
    exception and raise that::

       abort(404)
       abort(Response('Hello World'))

    """
    return _aborter(status, *args, **kwargs)


_aborter = Aborter()

#: An exception that is used to signal both a :exc:`KeyError` and a
#: :exc:`BadRequest`. Used by many of the datastructures.
BadRequestKeyError = BadRequest.wrap(KeyError)
