from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.errors import ApiError
from app.core.config import get_settings
from app.db.models import Artifact
from app.db.session import get_db
from app.schemas.api import (
    ArtifactEditRequest,
    DraftArtifactRead,
    PublishArtifactRequest,
    PublishArtifactResponse,
)
from app.services.export_service import format_artifact_export
from app.services.run_persistence import build_artifact_detail, create_artifact_version
from app.services.social_publish import publish_social_post

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}", response_model=DraftArtifactRead)
def get_artifact(artifact_id: str, db: Session = Depends(get_db)) -> DraftArtifactRead:
    art = db.get(Artifact, artifact_id)
    if art is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Artifact '{artifact_id}' was not found.",
        )
    return build_artifact_detail(db, art)


@router.put("/{artifact_id}", response_model=DraftArtifactRead)
def save_artifact_edit(
    artifact_id: str,
    payload: ArtifactEditRequest,
    db: Session = Depends(get_db),
) -> DraftArtifactRead:
    art = db.get(Artifact, artifact_id)
    if art is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Artifact '{artifact_id}' was not found.",
        )

    latest_ver = db.scalar(select(func.max(Artifact.version)).where(Artifact.run_id == art.run_id))
    latest_art = db.scalar(
        select(Artifact).where(Artifact.run_id == art.run_id, Artifact.version == latest_ver)
    )
    if (
        payload.expected_parent_version_id
        and latest_art is not None
        and payload.expected_parent_version_id != latest_art.id
    ):
        raise ApiError(
            status_code=409,
            code="INVALID_REQUEST",
            message=(
                "A newer artifact version already exists. Refresh to review the latest version before saving."
            ),
        )

    new_art = create_artifact_version(
        db,
        run_id=art.run_id,
        title=(payload.title.strip() if payload.title else art.title),
        hook=art.hook,
        body_markdown=payload.body_markdown,
        platform=art.platform,
        outline=art.outline_json or [],
        thread_segments=art.thread_segments_json or [],
        created_by="user",
        status="user_edited",
        parent_version_id=art.id,
        is_agent_approved=False,
    )
    db.commit()
    db.refresh(new_art)
    return build_artifact_detail(db, new_art)


@router.get("/{artifact_id}/export")
def export_artifact(
    artifact_id: str,
    format: str = Query(default="md", pattern="^(md|txt)$"),
    db: Session = Depends(get_db),
) -> Response:
    art = db.get(Artifact, artifact_id)
    if art is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Artifact '{artifact_id}' was not found.",
        )
    content, media_type, filename = format_artifact_export(art, fmt=format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{artifact_id}/publish", response_model=PublishArtifactResponse)
async def publish_artifact(
    artifact_id: str,
    payload: PublishArtifactRequest,
    db: Session = Depends(get_db),
) -> PublishArtifactResponse:
    art = db.get(Artifact, artifact_id)
    if art is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Artifact '{artifact_id}' was not found.",
        )
    return await publish_social_post(
        platform=payload.platform,
        text=payload.text,
        settings=get_settings(),
    )
