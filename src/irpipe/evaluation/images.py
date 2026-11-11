"""Two pictures compared: how many ink pixels disagree, and by how much on average.

    difference = compare(Path("reference.png"), Path("frame.png"))
    difference.same, difference.strong, difference.ink, difference.mean
    difference.save(Path("difference.png"))     # where they disagree, brightened

A pixel is ink when one of its channels is ``INK`` away from the
background (the colour of the top-left pixel); two pixels disagree
strongly when one of their channels differs by more than ``STRONG``. Two
pictures are the same when at most ``MAX_STRONG_SHARE`` of the ink
disagrees strongly and the mean difference over the whole frame is at most
``MAX_MEAN``: what antialiasing leaves. These are the numbers the backend
conformance tests use. Pictures of different sizes are never the same.

Needs Pillow and numpy, which come with the manim extra.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

INK: Final = 32
STRONG: Final = 128
MAX_STRONG_SHARE: Final = 0.001
MAX_MEAN: Final = 0.1


@dataclass(frozen=True)
class Difference:
    size: tuple[int, int]
    """The new picture's width and height, in pixels."""
    reference_size: tuple[int, int]
    ink: int
    """Ink pixels, in either picture."""
    strong: int
    """Pixels that disagree strongly."""
    mean: float
    """Mean difference over the frame, 0-255 (largest channel)."""
    pixels: Any = None
    """The difference itself (numpy, height x width), when the sizes match."""

    @property
    def same(self) -> bool:
        if self.size != self.reference_size:
            return False
        return self.strong <= MAX_STRONG_SHARE * max(self.ink, 1) and self.mean <= MAX_MEAN

    def describe(self) -> str:
        if self.size != self.reference_size:
            return f"size {self.size[0]}x{self.size[1]}, reference {self.reference_size[0]}x" \
                f"{self.reference_size[1]}"  # fmt: skip
        share = self.strong / max(self.ink, 1)
        return f"{self.strong} of {self.ink} ink pixels differ ({share:.2%}), mean {self.mean:.3f}"

    def save(self, path: Path) -> None:
        """The difference as a picture, three times brighter; nothing when sizes differ."""
        if self.pixels is None:
            return
        import numpy as np
        from PIL import Image

        Image.fromarray(np.clip(self.pixels * 3, 0, 255).astype(np.uint8)).save(path)


def compare(reference: Path, picture: Path) -> Difference:
    import numpy as np
    from PIL import Image

    old = np.asarray(Image.open(reference).convert("RGB"), dtype=np.int16)
    new = np.asarray(Image.open(picture).convert("RGB"), dtype=np.int16)
    size = (new.shape[1], new.shape[0])
    reference_size = (old.shape[1], old.shape[0])
    if old.shape != new.shape:
        return Difference(size, reference_size, 0, 0, 255.0)
    background = old[0, 0]
    ink = (np.abs(old - background).max(axis=2) > INK) | (
        np.abs(new - background).max(axis=2) > INK
    )
    difference = np.abs(old - new).max(axis=2)
    return Difference(
        size, reference_size, int(ink.sum()), int((difference > STRONG).sum()),
        float(difference.mean()), difference,
    )  # fmt: skip
