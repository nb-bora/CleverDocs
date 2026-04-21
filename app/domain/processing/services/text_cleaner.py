"""Text cleaner port (interface)."""


class TextCleaner:
    def clean(self, raw_text: str) -> str:
        raise NotImplementedError
