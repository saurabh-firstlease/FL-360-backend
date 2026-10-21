from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Hotspot, Scene, Tour
from app.schemas import TourSummary, media_url


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


async def load_tour(db: AsyncSession, tour_id: int) -> Tour:
    """Tour with every scene and hotspot, freshly read from the database."""
    stmt = (
        select(Tour)
        .where(Tour.id == tour_id)
        .options(selectinload(Tour.scenes).selectinload(Scene.hotspots))
        .execution_options(populate_existing=True)
    )
    tour = (await db.execute(stmt)).scalar_one_or_none()
    if tour is None:
        raise not_found("Tour")
    return tour


async def get_tour_row(db: AsyncSession, tour_id: int) -> Tour:
    tour = await db.get(Tour, tour_id, populate_existing=True)
    if tour is None:
        raise not_found("Tour")
    return tour


async def load_scene(db: AsyncSession, scene_id: int) -> Scene:
    stmt = (
        select(Scene)
        .where(Scene.id == scene_id)
        .options(selectinload(Scene.hotspots))
        .execution_options(populate_existing=True)
    )
    scene = (await db.execute(stmt)).scalar_one_or_none()
    if scene is None:
        raise not_found("Room")
    return scene


async def get_hotspot(db: AsyncSession, hotspot_id: int) -> Hotspot:
    hotspot = await db.get(Hotspot, hotspot_id, populate_existing=True)
    if hotspot is None:
        raise not_found("Hotspot")
    return hotspot


async def tour_summaries(
    db: AsyncSession, published_only: bool, property_ref: str | None = None
) -> list[TourSummary]:
    stmt = select(Tour).options(selectinload(Tour.scenes)).order_by(Tour.updated_at.desc())
    if published_only:
        stmt = stmt.where(Tour.published.is_(True))
    if property_ref:
        stmt = stmt.where(Tour.property_ref == property_ref)
    out = []
    for t in (await db.execute(stmt)).scalars():
        cover = next((s for s in t.scenes if s.id == t.start_scene_id), t.scenes[0] if t.scenes else None)
        out.append(
            TourSummary(
                id=t.id,
                title=t.title,
                description=t.description,
                property_ref=t.property_ref,
                published=t.published,
                scene_count=len(t.scenes),
                cover_url=media_url(cover.thumb_path) if cover else None,
                updated_at=t.updated_at,
            )
        )
    return out


async def validate_hotspot(db: AsyncSession, scene: Scene, data: dict) -> Scene | None:
    """Normalise a hotspot's fields for its type. Returns the target scene for nav hotspots."""
    kind = data["type"]
    if kind == "nav":
        target_id = data.get("target_scene_id")
        if target_id is None:
            raise invalid("Choose the room this hotspot leads to")
        if target_id == scene.id:
            raise invalid("A hotspot can't lead to the room it is in")
        target = await db.get(Scene, target_id)
        if target is None or target.tour_id != scene.tour_id:
            raise invalid("The target room must belong to the same tour")
        data["url"] = None
        return target
    data["target_scene_id"] = None
    if kind == "link":
        if not data.get("url"):
            raise invalid("Link hotspots need a URL")
    else:
        data["url"] = None
        if not data.get("label") and not data.get("description"):
            raise invalid("Info hotspots need a title or a description")
    return None
