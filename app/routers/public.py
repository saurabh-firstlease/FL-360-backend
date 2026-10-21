from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import is_admin
from app.database import get_db
from app.schemas import TourOut, TourSummary
from app.services.tours import load_tour, not_found, tour_summaries

router = APIRouter(tags=["public"])


@router.get("/tours", response_model=list[TourSummary])
async def list_published_tours(
    property_ref: str | None = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    return await tour_summaries(db, published_only=True, property_ref=property_ref)


@router.get("/tours/{tour_id}", response_model=TourOut)
async def get_tour(tour_id: int, admin: bool = Depends(is_admin), db: AsyncSession = Depends(get_db)):
    """Published tours are public. Admins can also load drafts (used for preview)."""
    tour = await load_tour(db, tour_id)
    if not tour.published and not admin:
        raise not_found("Tour")
    return tour
