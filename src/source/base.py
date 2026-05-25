from abc import ABC, abstractmethod
from src.models.product import ProductSource


class BaseSource(ABC):
    @abstractmethod
    def search(self, keyword: str, page: int = 1) -> list[ProductSource]:
        ...

    @abstractmethod
    def crawl_by_keywords(self, keywords: list[str]) -> list[ProductSource]:
        ...

    @abstractmethod
    def close(self):
        ...
