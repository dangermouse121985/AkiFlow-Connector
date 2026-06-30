from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class OperatorSettings:
    data_source: str = "sample"

    @property
    def use_akiflow(self) -> bool:
        return self.data_source.lower() in {"akiflow", "live"}


def load_settings() -> OperatorSettings:
    load_dotenv()
    return OperatorSettings(
        data_source=os.getenv("OPERATOR_DATA_SOURCE", "sample").strip().lower() or "sample",
    )
