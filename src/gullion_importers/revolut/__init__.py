import datetime

from beangulp.importers import csvbase


class RevolutDate(csvbase.Column):
    def __init__(self):
        super().__init__(
            "Completed Date",
            "Started Date",
        )

    def parse(self, completed, started):
        value = completed or started

        return datetime.datetime.strptime(
            value.strip(),
            "%Y-%m-%d %H:%M:%S",
        ).date()
