from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.schemas.analysis import AnalysisResponse, ConversationRequest
from app.services import analysis_service

router = APIRouter(prefix="/api")


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    dependencies=[Depends(get_current_user)],
)
def analyze_conversation(request: ConversationRequest) -> AnalysisResponse:
    analysis = analysis_service.analyze_conversation(request.conversation, request.user_name)
    return AnalysisResponse.from_analysis(analysis)
