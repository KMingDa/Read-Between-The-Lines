from typing import Self

from pydantic import BaseModel, Field

from app.services.analysis_service import ConversationAnalysis


class ConversationRequest(BaseModel):
    conversation: str = Field(min_length=1, max_length=10000)
    user_name: str = Field(min_length=1, max_length=100)


class AnalysisResponse(BaseModel):
    observation: str
    interpretation: str
    suggested_next_step: str
    is_demo: bool
    parsed_message_count: int
    reply_details: list[dict] = Field(default_factory=list)
    reply_times: list[float] = Field(default_factory=list)
    average_reply_time_minutes: float | None = None

    @classmethod
    def from_analysis(cls, analysis: ConversationAnalysis) -> Self:
        intervals = analysis.reply_intervals.intervals
        average = analysis.reply_intervals.average_minutes
        return cls(
            observation=analysis.observation,
            interpretation=analysis.interpretation,
            suggested_next_step=analysis.suggested_next_step,
            is_demo=analysis.is_demo,
            parsed_message_count=analysis.message_count,
            reply_details=[
                {"from": i.replier, "to": i.replied_to, "minutes": i.minutes} for i in intervals
            ],
            reply_times=[i.minutes for i in intervals],
            average_reply_time_minutes=None if average is None else round(average, 2),
        )
