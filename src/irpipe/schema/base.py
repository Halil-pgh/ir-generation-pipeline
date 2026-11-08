"""The base of every contract model: immutable, and strict about unknown fields.

A misspelled field (``"colour"``, ``"subtitles"``) is an error, never silently
ignored, and a model cannot be changed after it is validated: stages build
new objects instead of editing the ones they were given.
"""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
