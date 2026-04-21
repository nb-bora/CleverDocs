"""UnitOfWork port (transaction boundary)."""


class UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self) -> None:
        raise NotImplementedError
