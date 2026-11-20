from fastapi import APIRouter, Depends, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.schemas.conversations import (
    ConversationDetail,
    ConversationSummary,
    ImportResponse,
    MessagePage,
)
from app.api.schemas.errors import UNAUTHORIZED, error_response
from app.domain.entities import DateOrder
from app.infrastructure.models import User
from app.services import conversation_service

router = APIRouter(prefix="/api/conversations")

# OpenAPI documentation of the error responses; it does not change what the endpoints do.
NOT_FOUND = {
    404: error_response(
        "No such conversation, or it belongs to another user (the two look the same).",
        conversation_service.NOT_FOUND,
    )
}
IMPORT_ERRORS = {
    **UNAUTHORIZED,
    409: error_response("This user has already imported the same chat.", conversation_service.ALREADY_IMPORTED),
    413: error_response("The file is larger than 5 MB.", "The file is larger than 5 MB."),
    422: {
        "description": (
            "The upload is not a usable chat export (`detail` is a message), or a form field is "
            "missing or invalid (`detail` is FastAPI's list of validation errors)."
        ),
        "content": {
            "application/json": {
                "schema": {
                    "anyOf": [
                        {"$ref": "#/components/schemas/ErrorResponse"},
                        {"$ref": "#/components/schemas/HTTPValidationError"},
                    ]
                },
                "example": {"detail": "The file is empty."},
            }
        },
    },
}


@router.post("/import", status_code=status.HTTP_201_CREATED, responses=IMPORT_ERRORS)
def import_conversation(
    file: UploadFile,
    date_order: DateOrder | None = Form(default=None),  # leave out to detect it from the file
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResponse:
    # shortcut: FastAPI receives the whole request body before this point; a deployed server
    # must also cap request bodies at the reverse proxy or web server.
    data = file.file.read(conversation_service.MAX_IMPORT_BYTES + 1)
    result = conversation_service.import_whatsapp_export(
        db, user_id=user.id, filename=file.filename, data=data, date_order=date_order
    )
    return ImportResponse.from_result(result)


@router.get("", responses=UNAUTHORIZED)
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    return [
        ConversationSummary.model_validate(conversation)
        for conversation in conversation_service.list_conversations(db, user.id)
    ]


@router.get("/{conversation_id}", responses={**UNAUTHORIZED, **NOT_FOUND})
def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    overview = conversation_service.get_conversation_detail(db, user.id, conversation_id)
    return ConversationDetail.from_overview(overview)


@router.get("/{conversation_id}/messages", responses={**UNAUTHORIZED, **NOT_FOUND})
def get_messages(
    conversation_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessagePage:
    page = conversation_service.get_message_page(
        db, user.id, conversation_id, offset=offset, limit=limit
    )
    return MessagePage.from_slice(page, offset=offset, limit=limit)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**UNAUTHORIZED, **NOT_FOUND},
)
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    conversation_service.delete_conversation(db, user.id, conversation_id)
