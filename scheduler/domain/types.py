"""選股訊號資料契約。"""

from dataclasses import asdict, dataclass, field
from typing import Literal

SignalAction = Literal["buy", "watch", "reduce", "avoid"]


# 2026-02-15 調整方式: 新增 CandidateSignal 作為跨流程統一訊號契約。
@dataclass
class CandidateSignal:
    """統一輸出的候選訊號模型。"""

    stock_code: str
    signal_date: str
    technical_score: float
    news_score: float
    risk_penalty: float
    total_score: float
    action: SignalAction
    confidence: float
    reasons: list[str] = field(default_factory=list)
    source: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        payload = asdict(self)
        payload["technical_score"] = round(float(self.technical_score), 2)
        payload["news_score"] = round(float(self.news_score), 2)
        payload["risk_penalty"] = round(float(self.risk_penalty), 2)
        payload["total_score"] = round(float(self.total_score), 2)
        payload["confidence"] = round(float(self.confidence), 4)
        return payload
