from urllib.parse import quote

import httpx

from app.api.v1.errors import ApiError
from app.core.config import Settings
from app.schemas.api import PublishArtifactResponse
from app.schemas.common import PlatformType


def _composer_url(platform: PlatformType, text: str) -> str:
    if platform == "linkedin":
        return f"https://www.linkedin.com/feed/?shareActive=true&text={quote(text[:2900])}"
    if platform == "x":
        return f"https://x.com/intent/post?text={quote(text[:280])}"
    return "https://www.instagram.com/"


async def publish_social_post(
    *,
    platform: PlatformType,
    text: str,
    settings: Settings,
) -> PublishArtifactResponse:
    """Publish directly via connected social API when configured, or return a pre-filled composer URL."""
    clean_text = text.strip()
    if platform == "linkedin" and settings.is_linkedin_connected:
        author = settings.linkedin_person_urn.strip()
        if not author.startswith("urn:li:"):
            author = f"urn:li:person:{author}"
        payload = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": clean_text[:3000]},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        headers = {
            "Authorization": f"Bearer {settings.linkedin_access_token.strip()}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.linkedin.com/v2/ugcPosts",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise ApiError(
                status_code=502,
                code="SOCIAL_PUBLISH_FAILED",
                message="Could not reach LinkedIn right now. Your post is still copied and ready to paste.",
            ) from exc

        if resp.status_code >= 400:
            raise ApiError(
                status_code=502,
                code="SOCIAL_PUBLISH_FAILED",
                message=f"LinkedIn rejected the post (HTTP {resp.status_code}). Check your LINKEDIN_ACCESS_TOKEN or post via composer.",
            )

        post_id = resp.headers.get("x-restli-id") or ""
        post_url = f"https://www.linkedin.com/feed/update/{post_id}" if post_id else "https://www.linkedin.com/feed/"
        return PublishArtifactResponse(
            platform="linkedin",
            mode="direct_api",
            published=True,
            post_url=post_url,
            message="Published directly to your connected LinkedIn account.",
        )

    if platform == "x" and settings.is_x_connected:
        headers = {
            "Authorization": f"Bearer {settings.x_access_token.strip()}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.x.com/2/tweets",
                    json={"text": clean_text[:280]},
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise ApiError(
                status_code=502,
                code="SOCIAL_PUBLISH_FAILED",
                message="Could not reach X right now. Your post is still copied and ready to paste.",
            ) from exc

        if resp.status_code >= 400:
            raise ApiError(
                status_code=502,
                code="SOCIAL_PUBLISH_FAILED",
                message=f"X rejected the post (HTTP {resp.status_code}). Check your X_ACCESS_TOKEN or post via composer.",
            )

        tweet_id = ""
        try:
            tweet_id = str(resp.json().get("data", {}).get("id") or "")
        except ValueError:
            tweet_id = ""
        post_url = f"https://x.com/i/status/{tweet_id}" if tweet_id else "https://x.com/home"
        return PublishArtifactResponse(
            platform="x",
            mode="direct_api",
            published=True,
            post_url=post_url,
            message="Published directly to your connected X account.",
        )

    composer = _composer_url(platform, clean_text)
    if platform == "instagram":
        msg = "Formatted caption copied. Paste directly into Instagram to publish."
    else:
        msg = f"Opening {platform.title()} with your formatted post pre-filled and copied."
    return PublishArtifactResponse(
        platform=platform,
        mode="composer_ready",
        published=False,
        composer_url=composer,
        message=msg,
    )
