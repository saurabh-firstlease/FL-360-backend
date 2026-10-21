# FL 360 Walkthrough API

FastAPI + PostgreSQL backend for the 360° walkthrough. It stores tours, rooms (panoramas) and hotspots, and processes uploaded photos.

## Setup

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
createdb fl_tours
cp .env.example .env        # set DATABASE_URL and ADMIN_TOKEN
./venv/bin/alembic upgrade head
./venv/bin/uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

Frontend: in `../frontend`, set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local` and run `npm run dev` (or `npm run dev:all` to start this API too).
- Admin: http://localhost:3000/admin (sign in with `ADMIN_TOKEN`)
- Public tour: http://localhost:3000/tours/<id> (published tours only; `?scene=<id>` opens a room)

## Tests

```bash
createdb fl_tours_test
./venv/bin/python -m pytest -q
```

## Data model

| Table | Purpose |
|---|---|
| `tours` | title, `property_ref` (link to a listing on the main site), `published`, `start_scene_id`, floor plan |
| `scenes` | one 360° photo: image files, `heading`, start view (`initial_yaw`, `initial_pitch`), floor-plan position (`map_x`, `map_y` as 0–1), `sort_order` |
| `hotspots` | `type` = `nav` (go to `target_scene_id`), `info` (label + description) or `link` (`url`); position `yaw`, `pitch` |

Directions: `yaw`/`pitch` are photo coordinates in degrees (0 = photo centre, +yaw right, +pitch up).
A room's `heading` is the floor-plan direction its photo centre faces (0 = top of the plan), so
the world direction of anything in a photo is `yaw + heading`. Setting headings lines all rooms up,
which keeps the visitor's direction when walking between rooms and makes the floor-plan cone correct.

Deleting a room also deletes its hotspots and every hotspot that leads to it.

## Endpoints

Public:
- `GET /api/tours?property_ref=` – published tours
- `GET /api/tours/{id}` – full tour with rooms and hotspots (drafts too, with the admin token)

Admin (`Authorization: Bearer <ADMIN_TOKEN>`):
- `GET/POST /api/admin/tours`, `PATCH/DELETE /api/admin/tours/{id}`
- `PUT/DELETE /api/admin/tours/{id}/floorplan` (multipart `file`)
- `POST /api/admin/tours/{id}/scenes` (multipart `file`, optional `name`)
- `PUT /api/admin/tours/{id}/scenes/order` `{"scene_ids": [...]}`
- `PATCH/DELETE /api/admin/scenes/{id}`, `PUT /api/admin/scenes/{id}/image`
- `POST /api/admin/scenes/{id}/hotspots` (`add_return: true` also creates the way back)
- `PATCH/DELETE /api/admin/hotspots/{id}`

## Uploads

Panoramas must be 2:1 equirectangular JPEG/PNG/WebP (≤ `MAX_UPLOAD_MB`). Each upload is re-encoded
with Pillow (metadata stripped) into `full.jpg` (≤ 4096 px wide, safe for phone GPUs), `preview.jpg`
(1024 px, shown first) and `thumb.jpg`, stored under `MEDIA_ROOT` and served from `/media` with
long-lived cache headers. Behind a CDN or object storage, point `MEDIA_URL` at it.

## Production notes

- Use a long random `ADMIN_TOKEN` and HTTPS. This is a single shared admin token; swap `app/core/security.py`
  for real user accounts if several people need separate logins.
- Set `CORS_ORIGINS` to the real frontend origin(s) and `PUBLIC_BASE_URL` / `MEDIA_URL` to public URLs.
- Back up `MEDIA_ROOT` together with the database.
# FL-360-backend
