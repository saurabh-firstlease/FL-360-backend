"""Panorama and floor-plan processing.

Every upload is re-encoded with Pillow, so nothing the user sent is served as-is
(no EXIF, no polyglot files). Each panorama gets three files:

- full.jpg     up to PANO_FULL_WIDTH wide (4096 by default, safe on phones)
- preview.jpg  1024 wide, shown while full.jpg loads
- thumb.jpg    480x300 crop of the photo centre, for room cards
"""
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import MAX_UPLOAD_BYTES, MEDIA_ROOT, PANO_FULL_WIDTH, PANO_PREVIEW_WIDTH

Image.MAX_IMAGE_PIXELS = 200_000_000  # ~20000x10000; Pillow's default rejects big 360 cameras

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
THUMB_SIZE = (480, 300)
FLOORPLAN_MAX_SIDE = 2400


class ImageError(ValueError):
    pass


@dataclass
class PanoFiles:
    image_path: str
    preview_path: str
    thumb_path: str
    width: int
    height: int


async def save_upload(file: UploadFile) -> Path:
    """Stream an upload to a temp file, enforcing MAX_UPLOAD_BYTES."""
    fd, tmp = tempfile.mkstemp(suffix=".upload")
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                    )
                out.write(chunk)
    except BaseException:
        os.unlink(tmp)
        raise
    if size == 0:
        os.unlink(tmp)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="File is empty")
    return Path(tmp)


def _open(src: Path) -> Image.Image:
    try:
        im = Image.open(src)
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImageError("Not a readable image (use JPEG, PNG or WebP)") from e
    if im.format not in ALLOWED_FORMATS:
        raise ImageError(f"Unsupported image format {im.format}; use JPEG, PNG or WebP")
    return im


def _resize_width(im: Image.Image, width: int) -> Image.Image:
    if im.width <= width:
        return im
    return im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)


def _save_jpeg(im: Image.Image, path: Path, quality: int) -> None:
    im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)


def process_panorama(src: Path) -> PanoFiles:
    with _open(src) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")
    w, h = im.size
    if not 1.9 <= w / h <= 2.1:
        raise ImageError(f"Not a 360° panorama: expected a 2:1 equirectangular image, got {w}x{h}")

    rel = Path("scenes") / uuid.uuid4().hex
    out = MEDIA_ROOT / rel
    out.mkdir(parents=True, exist_ok=True)
    try:
        full = _resize_width(im, PANO_FULL_WIDTH)
        _save_jpeg(full, out / "full.jpg", 85)
        _save_jpeg(_resize_width(full, PANO_PREVIEW_WIDTH), out / "preview.jpg", 75)

        # 90° wide crop around the photo centre (horizon), roughly what a 16:10 camera sees.
        fw, fh = full.size
        cw, ch = fw / 4, fh * 0.31
        box = (round(fw / 2 - cw / 2), round(fh / 2 - ch / 2), round(fw / 2 + cw / 2), round(fh / 2 + ch / 2))
        thumb = ImageOps.fit(full.crop(box), THUMB_SIZE, Image.Resampling.LANCZOS)
        _save_jpeg(thumb, out / "thumb.jpg", 80)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise

    return PanoFiles(
        image_path=str(rel / "full.jpg"),
        preview_path=str(rel / "preview.jpg"),
        thumb_path=str(rel / "thumb.jpg"),
        width=full.width,
        height=full.height,
    )


def process_floorplan(src: Path) -> str:
    with _open(src) as raw:
        im = ImageOps.exif_transpose(raw)
        has_alpha = im.mode in ("RGBA", "LA", "P") and raw.format == "PNG"
        im = im.convert("RGBA" if has_alpha else "RGB")
    im.thumbnail((FLOORPLAN_MAX_SIDE, FLOORPLAN_MAX_SIDE), Image.Resampling.LANCZOS)

    rel_dir = Path("floorplans")
    (MEDIA_ROOT / rel_dir).mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    if has_alpha:
        rel = rel_dir / f"{name}.png"
        im.save(MEDIA_ROOT / rel, "PNG", optimize=True)
    else:
        rel = rel_dir / f"{name}.jpg"
        _save_jpeg(im, MEDIA_ROOT / rel, 88)
    return str(rel)


def delete_scene_files(image_path: str | None) -> None:
    """Remove a scene's folder (scenes/<uuid>/) given any of its file paths."""
    if not image_path:
        return
    folder = (MEDIA_ROOT / image_path).parent
    if folder.parent == MEDIA_ROOT / "scenes":
        shutil.rmtree(folder, ignore_errors=True)


def delete_media_file(path: str | None) -> None:
    if not path:
        return
    target = (MEDIA_ROOT / path).resolve()
    if MEDIA_ROOT in target.parents:
        target.unlink(missing_ok=True)


_EXT = re.compile(r"\.(jpe?g|png|webp)$", re.I)


def name_from_filename(filename: str | None) -> str:
    """'01 Conference Room.jpg.jpeg' -> 'Conference Room'."""
    stem = Path(filename or "").name
    while _EXT.search(stem):
        stem = _EXT.sub("", stem)
    stem = re.sub(r"^[\d\s._-]+", "", stem)
    stem = re.sub(r"[_]+", " ", stem).strip()
    return (stem or "Room")[:120]


def image_size(path: str | None) -> tuple[int, int] | None:
    if not path:
        return None
    try:
        with Image.open(MEDIA_ROOT / path) as im:
            return im.size
    except OSError:
        return None
