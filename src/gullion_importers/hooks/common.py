from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractedFile:
    filename: str
    entries: list
    account: str | None = None
    importer: Any = None
    extended: bool = False


def unpack_extracted(item) -> ExtractedFile:
    if len(item) == 4:
        filename, entries, account, importer = item

        return ExtractedFile(
            filename=filename,
            entries=entries,
            account=account,
            importer=importer,
            extended=True,
        )

    if len(item) == 2:
        filename, entries = item

        return ExtractedFile(
            filename=filename,
            entries=entries,
        )

    raise ValueError(f"Unexpected extracted item format: {item!r}")


def pack_extracted(
    item: ExtractedFile,
    entries: list,
):
    if item.extended:
        return (
            item.filename,
            entries,
            item.account,
            item.importer,
        )

    return (
        item.filename,
        entries,
    )
