from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):

    @abstractmethod
    def normalize(
        self,
        payload: dict[str, Any]
    ) -> dict:
        """외부 API 데이터를 공통 형식으로 변환"""
        pass