from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.database import get_db
from app.models import Hotspot, Scene, Tour
from app.schemas import (
    AutoConnectOut,
    HotspotCreate,
    HotspotOut,
    HotspotUpdate,
    SceneOrder,
    SceneOut,
    SceneUpdate,
    TourCreate,
    TourOut,
    TourSummary,
    TourUpdate,
    wrap180,
)
from app.services.images import (
    ImageError,
    PanoFiles,
    delete_media_file,
    delete_scene_files,
    image_size,
    name_from_filename,
    process_floorplan,
    process_panorama,
    save_upload,
)
from app.services.connect import plan_links
from app.services.tours import (
    get_hotspot,
    get_tour_row,
    invalid,
    load_scene,
    load_tour,
    tour_summaries,
    validate_hotspot,
)

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])

def no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _drop_nulls(data: dict, nullable: set[str]) -> dict:
    """PATCH bodies may send null only for columns that can be null."""
    return {k: v for k, v in data.items() if v is not None or k in nullable}


async def _process_pano(file: UploadFile) -> PanoFiles:
    tmp = await save_upload(file)
    try:
        return await run_in_threadpool(process_panorama, tmp)
    except ImageError as e:
        raise invalid(str(e))
    finally:
        tmp.unlink(missing_ok=True)


# ---------------- Tours ----------------

@router.get("/tours", response_model=list[TourSummary])
async def list_tours(db: AsyncSession = Depends(get_db)):
    return await tour_summaries(db, published_only=False)


@router.post("/tours", response_model=TourOut, status_code=status.HTTP_201_CREATED)
async def create_tour(body: TourCreate, db: AsyncSession = Depends(get_db)):
    tour = Tour(**body.model_dump())
    db.add(tour)
    await db.commit()
    return await load_tour(db, tour.id)


@router.patch("/tours/{tour_id}", response_model=TourOut)
async def update_tour(tour_id: int, body: TourUpdate, db: AsyncSession = Depends(get_db)):
    tour = await load_tour(db, tour_id)
    data = _drop_nulls(body.model_dump(exclude_unset=True), {"description", "property_ref", "start_scene_id"})
    start = data.get("start_scene_id")
    if start is not None and start not in {s.id for s in tour.scenes}:
        raise invalid("The start room must belong to this tour")
    if data.get("published") and not tour.scenes:
        raise invalid("Add at least one room before publishing")
    for key, value in data.items():
        setattr(tour, key, value)
    await db.commit()
    return await load_tour(db, tour_id)


@router.delete("/tours/{tour_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tour(tour_id: int, db: AsyncSession = Depends(get_db)):
    tour = await load_tour(db, tour_id)
    files = [s.image_path for s in tour.scenes]
    floorplan = tour.floorplan_path
    await db.execute(delete(Tour).where(Tour.id == tour_id))
    await db.commit()
    for path in files:
        delete_scene_files(path)
    delete_media_file(floorplan)
    return no_content()


@router.put("/tours/{tour_id}/floorplan", response_model=TourOut)
async def upload_floorplan(tour_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    tour = await get_tour_row(db, tour_id)
    tmp = await save_upload(file)
    try:
        path = await run_in_threadpool(process_floorplan, tmp)
    except ImageError as e:
        raise invalid(str(e))
    finally:
        tmp.unlink(missing_ok=True)
    old = tour.floorplan_path
    tour.floorplan_path = path
    await db.commit()
    delete_media_file(old)
    return await load_tour(db, tour_id)


@router.delete("/tours/{tour_id}/floorplan", response_model=TourOut)
async def delete_floorplan(tour_id: int, db: AsyncSession = Depends(get_db)):
    tour = await get_tour_row(db, tour_id)
    old = tour.floorplan_path
    tour.floorplan_path = None
    await db.commit()
    delete_media_file(old)
    return await load_tour(db, tour_id)


# ---------------- Scenes (rooms) ----------------

@router.post("/tours/{tour_id}/scenes", response_model=SceneOut, status_code=status.HTTP_201_CREATED)
async def upload_scene(
    tour_id: int,
    file: UploadFile = File(...),
    name: str | None = Form(None, max_length=120),
    db: AsyncSession = Depends(get_db),
):
    tour = await get_tour_row(db, tour_id)
    files = await _process_pano(file)
    try:
        last = await db.execute(
            select(func.coalesce(func.max(Scene.sort_order), -1)).where(Scene.tour_id == tour_id)
        )
        scene = Scene(
            tour_id=tour_id,
            name=(name or "").strip() or name_from_filename(file.filename),
            sort_order=last.scalar_one() + 1,
            **asdict(files),
        )
        db.add(scene)
        await db.flush()
        if tour.start_scene_id is None:
            tour.start_scene_id = scene.id
        await db.commit()
    except BaseException:
        delete_scene_files(files.image_path)
        raise
    return await load_scene(db, scene.id)


@router.put("/tours/{tour_id}/scenes/order", response_model=TourOut)
async def reorder_scenes(tour_id: int, body: SceneOrder, db: AsyncSession = Depends(get_db)):
    tour = await load_tour(db, tour_id)
    by_id = {s.id: s for s in tour.scenes}
    if sorted(body.scene_ids) != sorted(by_id):
        raise invalid("scene_ids must list every room in the tour exactly once")
    for i, scene_id in enumerate(body.scene_ids):
        by_id[scene_id].sort_order = i
    await db.commit()
    return await load_tour(db, tour_id)


@router.patch("/scenes/{scene_id}", response_model=SceneOut)
async def update_scene(scene_id: int, body: SceneUpdate, db: AsyncSession = Depends(get_db)):
    scene = await load_scene(db, scene_id)
    data = _drop_nulls(body.model_dump(exclude_unset=True), {"description", "map_x", "map_y"})
    for key, value in data.items():
        setattr(scene, key, value)
    await db.commit()
    return await load_scene(db, scene_id)


@router.put("/scenes/{scene_id}/image", response_model=SceneOut)
async def replace_scene_image(scene_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    scene = await load_scene(db, scene_id)
    files = await _process_pano(file)
    old = scene.image_path
    for key, value in asdict(files).items():
        setattr(scene, key, value)
    try:
        await db.commit()
    except BaseException:
        delete_scene_files(files.image_path)
        raise
    delete_scene_files(old)
    return await load_scene(db, scene_id)


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    scene = await load_scene(db, scene_id)
    tour_id, path = scene.tour_id, scene.image_path
    # The database removes its hotspots, hotspots pointing at it, and clears tours.start_scene_id.
    await db.execute(delete(Scene).where(Scene.id == scene_id))
    tour = await get_tour_row(db, tour_id)
    if tour.start_scene_id is None:
        first = await db.execute(
            select(Scene.id).where(Scene.tour_id == tour_id).order_by(Scene.sort_order, Scene.id).limit(1)
        )
        tour.start_scene_id = first.scalar_one_or_none()
        if tour.start_scene_id is None:
            tour.published = False
    await db.commit()
    delete_scene_files(path)
    return no_content()


@router.post("/tours/{tour_id}/auto-connect", response_model=AutoConnectOut)
async def auto_connect(tour_id: int, db: AsyncSession = Depends(get_db)):
    """Link every room to its neighbours with walk circles (see services/connect.py)."""
    tour = await load_tour(db, tour_id)
    if len(tour.scenes) < 2:
        raise invalid("Upload at least two rooms first")
    existing = {
        (s.id, h.target_scene_id): (h.yaw + s.heading, h.pitch)
        for s in tour.scenes
        for h in s.hotspots
        if h.type == "nav" and h.target_scene_id is not None
    }
    size = await run_in_threadpool(image_size, tour.floorplan_path)
    links = plan_links(list(tour.scenes), existing, size)
    for link in links:
        db.add(Hotspot(scene_id=link.source_id, type="nav", target_scene_id=link.target_id, yaw=link.yaw, pitch=link.pitch))
    await db.commit()
    return AutoConnectOut(created=len(links), tour=await load_tour(db, tour_id))


# ---------------- Hotspots ----------------

@router.post("/scenes/{scene_id}/hotspots", response_model=HotspotOut, status_code=status.HTTP_201_CREATED)
async def create_hotspot(scene_id: int, body: HotspotCreate, db: AsyncSession = Depends(get_db)):
    scene = await load_scene(db, scene_id)
    data = body.model_dump(exclude={"add_return"})
    target = await validate_hotspot(db, scene, data)
    hotspot = Hotspot(scene_id=scene_id, **data)
    db.add(hotspot)

    if body.add_return and target is not None:
        existing = await db.execute(
            select(Hotspot.id).where(
                Hotspot.scene_id == target.id, Hotspot.type == "nav", Hotspot.target_scene_id == scene_id
            )
        )
        if existing.first() is None:
            # Same spot seen from the other room: the opposite compass bearing.
            bearing = data["yaw"] + scene.heading
            db.add(
                Hotspot(
                    scene_id=target.id,
                    type="nav",
                    target_scene_id=scene_id,
                    yaw=wrap180(bearing + 180 - target.heading),
                    pitch=data["pitch"],
                )
            )
    await db.commit()
    await db.refresh(hotspot)
    return hotspot


@router.patch("/hotspots/{hotspot_id}", response_model=HotspotOut)
async def update_hotspot(hotspot_id: int, body: HotspotUpdate, db: AsyncSession = Depends(get_db)):
    hotspot = await get_hotspot(db, hotspot_id)
    scene = await load_scene(db, hotspot.scene_id)
    changes = _drop_nulls(body.model_dump(exclude_unset=True), {"target_scene_id", "label", "description", "url"})
    merged = {
        "type": hotspot.type,
        "target_scene_id": hotspot.target_scene_id,
        "yaw": hotspot.yaw,
        "pitch": hotspot.pitch,
        "label": hotspot.label,
        "description": hotspot.description,
        "url": hotspot.url,
        **changes,
    }
    await validate_hotspot(db, scene, merged)
    for key, value in merged.items():
        setattr(hotspot, key, value)
    await db.commit()
    await db.refresh(hotspot)
    return hotspot


@router.delete("/hotspots/{hotspot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hotspot(hotspot_id: int, db: AsyncSession = Depends(get_db)):
    await get_hotspot(db, hotspot_id)
    await db.execute(delete(Hotspot).where(Hotspot.id == hotspot_id))
    await db.commit()
    return no_content()
