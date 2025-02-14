"""route factories."""
from typing import Any, Callable, Dict, List, Optional, Type, TypedDict, Union

from fastapi import Depends, params
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Match

from stac_fastapi.api.models import APIRequest


def _wrap_response(resp: Any, response_class: Type[Response]) -> Response:
    if isinstance(resp, Response):
        return resp
    else:
        return response_class(resp)


def create_async_endpoint(
    func: Callable,
    request_model: Union[Type[APIRequest], Type[BaseModel], Dict],
    response_class: Type[Response] = JSONResponse,
):
    """Wrap a coroutine in another coroutine which may be used to create a FastAPI endpoint."""
    if issubclass(request_model, APIRequest):

        async def _endpoint(
            request: Request,
            request_data: request_model = Depends(),  # type:ignore
        ):
            """Endpoint."""
            return _wrap_response(
                await func(request=request, **request_data.kwargs()), response_class
            )

    elif issubclass(request_model, BaseModel):

        async def _endpoint(
            request: Request,
            request_data: request_model,  # type:ignore
        ):
            """Endpoint."""
            return _wrap_response(
                await func(request_data, request=request), response_class
            )

    else:

        async def _endpoint(
            request: Request,
            request_data: Dict[str, Any],  # type:ignore
        ):
            """Endpoint."""
            return _wrap_response(
                await func(request_data, request=request), response_class
            )

    return _endpoint


def create_sync_endpoint(
    func: Callable,
    request_model: Union[Type[APIRequest], Type[BaseModel], Dict],
    response_class: Type[Response] = JSONResponse,
):
    """Wrap a function in another function which may be used to create a FastAPI endpoint."""
    if issubclass(request_model, APIRequest):

        def _endpoint(
            request: Request,
            request_data: request_model = Depends(),  # type:ignore
        ):
            """Endpoint."""
            return _wrap_response(
                func(request=request, **request_data.kwargs()), response_class
            )

    elif issubclass(request_model, BaseModel):

        def _endpoint(
            request: Request,
            request_data: request_model,  # type:ignore
        ):
            """Endpoint."""
            return _wrap_response(func(request_data, request=request), response_class)

    else:

        def _endpoint(
            request: Request,
            request_data: Dict[str, Any],  # type:ignore
        ):
            """Endpoint."""
            return _wrap_response(func(request_data, request=request), response_class)

    return _endpoint


class Scope(TypedDict, total=False):
    """More strict version of Starlette's Scope."""

    # https://github.com/encode/starlette/blob/6af5c515e0a896cbf3f86ee043b88f6c24200bcf/starlette/types.py#L3
    path: str
    method: str
    type: Optional[str]


def add_route_dependencies(
    routes: List[BaseRoute], scopes: List[Scope], dependencies=List[params.Depends]
) -> None:
    """Add dependencies to routes.

    Allows a developer to add dependencies to a route after the route has been
    defined.

    Returns:
        None
    """
    for scope in scopes:
        for route in routes:

            match, _ = route.matches({"type": "http", **scope})
            if match != Match.FULL:
                continue

            # Mimicking how APIRoute handles dependencies:
            # https://github.com/tiangolo/fastapi/blob/1760da0efa55585c19835d81afa8ca386036c325/fastapi/routing.py#L408-L412
            for depends in dependencies[::-1]:
                route.dependant.dependencies.insert(
                    0,
                    get_parameterless_sub_dependant(
                        depends=depends, path=route.path_format
                    ),
                )

            # Register dependencies directly on route so that they aren't ignored if
            # the routes are later associated with an app (e.g. app.include_router(router))
            # https://github.com/tiangolo/fastapi/blob/58ab733f19846b4875c5b79bfb1f4d1cb7f4823f/fastapi/applications.py#L337-L360
            # https://github.com/tiangolo/fastapi/blob/58ab733f19846b4875c5b79bfb1f4d1cb7f4823f/fastapi/routing.py#L677-L678
            route.dependencies.extend(dependencies)
