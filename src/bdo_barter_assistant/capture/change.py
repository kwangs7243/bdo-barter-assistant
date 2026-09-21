from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops, ImageStat


@dataclass(frozen=True)
class ViewportChangeConfig:
    """Tunable, dependency-free viewport change detection settings."""

    threshold: float = 0.02
    sample_size: tuple[int, int] = (96, 48)

    def __post_init__(self) -> None:
        if not 0.0 < self.threshold < 1.0:
            raise ValueError("change threshold must be between 0 and 1")
        if self.sample_size[0] <= 0 or self.sample_size[1] <= 0:
            raise ValueError("change sample size must be positive")


def viewport_fingerprint(
    image: Image.Image, config: ViewportChangeConfig
) -> Image.Image:
    """Create a small grayscale frame used only for local difference checks."""
    return image.convert("L").resize(config.sample_size, Image.Resampling.BILINEAR)


def viewport_difference(left: Image.Image, right: Image.Image) -> float:
    """Return normalized mean absolute grayscale difference in the 0..1 range."""
    if left.size != right.size:
        raise ValueError("viewport fingerprints must have the same size")
    difference = ImageChops.difference(left, right)
    return float(ImageStat.Stat(difference).mean[0] / 255.0)


def viewport_changed(
    left: Image.Image, right: Image.Image, config: ViewportChangeConfig
) -> bool:
    return viewport_difference(left, right) > config.threshold
