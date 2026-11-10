"""The base of every contract model: immutable, and strict about unknown fields.

A misspelled field (``"colour"``, ``"subtitles"``) is an error, never silently
ignored, and a model cannot be changed after it is validated: stages build
new objects instead of editing the ones they were given.

A field whose JSON name is a Python keyword (``"in"``) has another name in
Python (``space``); the JSON name is the only one a file may use, and the one
a model is written back with.
"""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", serialize_by_alias=True)
