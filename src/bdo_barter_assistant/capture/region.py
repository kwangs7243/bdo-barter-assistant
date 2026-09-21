from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def parse(cls, value: str) -> "Region":
        """Parse the CLI form ``x,y,width,height``."""
        try:
            parts = tuple(int(part.strip()) for part in value.split(","))
        except ValueError as exc:
            raise ValueError("region must contain four integers") from exc
        if len(parts) != 4:
            raise ValueError("region must use x,y,width,height")
        return cls(*parts)

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.width, self.height]


@dataclass(frozen=True)
class NormalizedRegion:
    """A client-area-relative region using values in the inclusive 0..1 range."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(value < 0.0 for value in values):
            raise ValueError("normalized region values cannot be negative")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("normalized region size must be positive")
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("normalized region must stay within the client area")

    @classmethod
    def from_pixels(
        cls, region: Region, client_size: tuple[int, int]
    ) -> "NormalizedRegion":
        width, height = client_size
        if width <= 0 or height <= 0:
            raise ValueError("client size must be positive")
        if (
            region.x < 0
            or region.y < 0
            or region.width <= 0
            or region.height <= 0
            or region.x + region.width > width
            or region.y + region.height > height
        ):
            raise ValueError("pixel region must stay within the client area")
        return cls(
            x=region.x / width,
            y=region.y / height,
            width=region.width / width,
            height=region.height / height,
        )

    def to_pixels(self, client_size: tuple[int, int]) -> Region:
        width, height = client_size
        if width <= 0 or height <= 0:
            raise ValueError("client size must be positive")
        left = round(self.x * width)
        top = round(self.y * height)
        right = round((self.x + self.width) * width)
        bottom = round((self.y + self.height) * height)
        return Region(left, top, right - left, bottom - top)

    def as_list(self) -> list[float]:
        return [self.x, self.y, self.width, self.height]


def crop_region(image: Image.Image, region: Region | None) -> Image.Image:
    """Return a validated manual barter-area crop or the original image."""
    if region is None:
        return image.copy()
    if region.x < 0 or region.y < 0 or region.width <= 0 or region.height <= 0:
        raise ValueError("region coordinates and size must be positive")
    right = region.x + region.width
    bottom = region.y + region.height
    if right > image.width or bottom > image.height:
        raise ValueError(
            f"region {(region.x, region.y, region.width, region.height)} "
            f"exceeds image size {image.size}"
        )
    return image.crop((region.x, region.y, right, bottom))
