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

