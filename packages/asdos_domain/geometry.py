"""Normalized, reversible page-coordinate transforms."""

from __future__ import annotations

from collections.abc import Sequence

from .scoring import DomainError

Point = tuple[float, float]


def _unit(value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise DomainError("normalized coordinate must be in [0, 1]")
    return value


def rotate_point(point: Point, clockwise_degrees: int) -> Point:
    x, y = (_unit(float(point[0])), _unit(float(point[1])))
    turns = clockwise_degrees % 360
    if turns not in {0, 90, 180, 270}:
        raise DomainError("only right-angle rotations are supported")
    return {
        0: (x, y),
        90: (1.0 - y, x),
        180: (1.0 - x, 1.0 - y),
        270: (y, 1.0 - x),
    }[turns]


def inverse_rotate_point(point: Point, clockwise_degrees: int) -> Point:
    return rotate_point(point, -clockwise_degrees)


def transform_polygon(polygon: Sequence[Point], clockwise_degrees: int) -> tuple[Point, ...]:
    if len(polygon) < 3:
        raise DomainError("a polygon needs at least three points")
    return tuple(rotate_point(point, clockwise_degrees) for point in polygon)


def display_to_normalized(
    point: Point,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    zoom: float = 1.0,
) -> Point:
    if width <= 0 or height <= 0 or zoom <= 0:
        raise DomainError("display bounds and zoom must be positive")
    x = (point[0] - left) / (width * zoom)
    y = (point[1] - top) / (height * zoom)
    return (_unit(x), _unit(y))
