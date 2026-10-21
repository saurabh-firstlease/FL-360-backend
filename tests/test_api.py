import pytest

from tests.conftest import ADMIN, make_image

pytestmark = pytest.mark.anyio


async def create_tour(client, title="Office"):
    r = await client.post("/api/admin/tours", json={"title": title}, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


async def upload_scene(client, tour_id, filename="01 Conference Room.jpg.jpeg", size=(2000, 1000)):
    files = {"file": (filename, make_image(*size), "image/jpeg")}
    return await client.post(f"/api/admin/tours/{tour_id}/scenes", files=files, headers=ADMIN)


async def test_admin_routes_require_token(client):
    assert (await client.get("/api/admin/tours")).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert (await client.post("/api/admin/tours", json={"title": "x"}, headers=bad)).status_code == 401


async def test_upload_creates_room_and_start_scene(client):
    tour = await create_tour(client)
    r = await upload_scene(client, tour["id"])
    assert r.status_code == 201, r.text
    scene = r.json()
    assert scene["name"] == "Conference Room"
    assert scene["width"] == 2000 and scene["height"] == 1000
    for key in ("image_url", "preview_url", "thumb_url"):
        assert scene[key].startswith("http")

    full = (await client.get(f"/api/tours/{tour['id']}", headers=ADMIN)).json()
    assert full["start_scene_id"] == scene["id"]

    media = await client.get("/media" + scene["thumb_url"].split("/media", 1)[1])
    assert media.status_code == 200
    assert "immutable" in media.headers["cache-control"]


async def test_rejects_non_panorama_and_garbage(client):
    tour = await create_tour(client)
    r = await upload_scene(client, tour["id"], size=(1600, 1200))
    assert r.status_code == 422
    assert "2:1" in r.json()["detail"]

    files = {"file": ("evil.jpg", b"<script>alert(1)</script>", "image/jpeg")}
    r = await client.post(f"/api/admin/tours/{tour['id']}/scenes", files=files, headers=ADMIN)
    assert r.status_code == 422


async def test_unpublished_tour_hidden_from_public(client):
    tour = await create_tour(client)
    assert (await client.get(f"/api/tours/{tour['id']}")).status_code == 404

    r = await client.patch(f"/api/admin/tours/{tour['id']}", json={"published": True}, headers=ADMIN)
    assert r.status_code == 422  # no rooms yet

    await upload_scene(client, tour["id"])
    r = await client.patch(f"/api/admin/tours/{tour['id']}", json={"published": True}, headers=ADMIN)
    assert r.status_code == 200
    assert (await client.get(f"/api/tours/{tour['id']}")).status_code == 200
    ids = [t["id"] for t in (await client.get("/api/tours")).json()]
    assert tour["id"] in ids


async def test_nav_hotspot_with_return_link(client):
    tour = await create_tour(client)
    a = (await upload_scene(client, tour["id"], "Reception.jpg")).json()
    b = (await upload_scene(client, tour["id"], "Cafe.jpg")).json()
    await client.patch(f"/api/admin/scenes/{a['id']}", json={"heading": 10}, headers=ADMIN)
    await client.patch(f"/api/admin/scenes/{b['id']}", json={"heading": -20}, headers=ADMIN)

    r = await client.post(
        f"/api/admin/scenes/{a['id']}/hotspots",
        json={"type": "nav", "target_scene_id": b["id"], "yaw": 30, "pitch": -20, "add_return": True},
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text

    full = (await client.get(f"/api/tours/{tour['id']}", headers=ADMIN)).json()
    back = next(s for s in full["scenes"] if s["id"] == b["id"])["hotspots"]
    assert len(back) == 1
    # bearing 30+10=40 from A, so 220 from B, which is 220-(-20)=240 -> -120 in B's photo
    assert back[0]["target_scene_id"] == a["id"]
    assert back[0]["yaw"] == pytest.approx(-120)


async def test_hotspot_validation(client):
    tour = await create_tour(client)
    other = await create_tour(client, "Other")
    a = (await upload_scene(client, tour["id"])).json()
    foreign = (await upload_scene(client, other["id"])).json()
    url = f"/api/admin/scenes/{a['id']}/hotspots"

    cases = [
        {"type": "nav", "yaw": 0, "pitch": 0},  # no target
        {"type": "nav", "target_scene_id": a["id"], "yaw": 0, "pitch": 0},  # itself
        {"type": "nav", "target_scene_id": foreign["id"], "yaw": 0, "pitch": 0},  # other tour
        {"type": "link", "yaw": 0, "pitch": 0, "url": "javascript:alert(1)"},
        {"type": "info", "yaw": 0, "pitch": 0},  # empty
        {"type": "info", "yaw": 0, "pitch": 120, "label": "x"},  # pitch out of range
    ]
    for body in cases:
        r = await client.post(url, json=body, headers=ADMIN)
        assert r.status_code == 422, (body, r.text)

    r = await client.post(url, json={"type": "link", "yaw": 190, "pitch": 0, "url": "https://firstlease.in"}, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["yaw"] == pytest.approx(-170)


async def test_delete_scene_moves_start_and_removes_links(client):
    tour = await create_tour(client)
    a = (await upload_scene(client, tour["id"], "A.jpg")).json()
    b = (await upload_scene(client, tour["id"], "B.jpg")).json()
    await client.post(
        f"/api/admin/scenes/{b['id']}/hotspots",
        json={"type": "nav", "target_scene_id": a["id"], "yaw": 0, "pitch": -10},
        headers=ADMIN,
    )
    assert (await client.delete(f"/api/admin/scenes/{a['id']}", headers=ADMIN)).status_code == 204

    full = (await client.get(f"/api/tours/{tour['id']}", headers=ADMIN)).json()
    assert [s["id"] for s in full["scenes"]] == [b["id"]]
    assert full["start_scene_id"] == b["id"]
    assert full["scenes"][0]["hotspots"] == []


async def test_reorder_and_floorplan(client):
    tour = await create_tour(client)
    a = (await upload_scene(client, tour["id"], "A.jpg")).json()
    b = (await upload_scene(client, tour["id"], "B.jpg")).json()

    r = await client.put(
        f"/api/admin/tours/{tour['id']}/scenes/order", json={"scene_ids": [b["id"], a["id"]]}, headers=ADMIN
    )
    assert [s["id"] for s in r.json()["scenes"]] == [b["id"], a["id"]]
    bad = await client.put(f"/api/admin/tours/{tour['id']}/scenes/order", json={"scene_ids": [a["id"]]}, headers=ADMIN)
    assert bad.status_code == 422

    files = {"file": ("plan.png", make_image(800, 600, "PNG"), "image/png")}
    r = await client.put(f"/api/admin/tours/{tour['id']}/floorplan", files=files, headers=ADMIN)
    assert r.status_code == 200 and r.json()["floorplan_url"]

    r = await client.patch(f"/api/admin/scenes/{a['id']}", json={"map_x": 0.25, "map_y": 0.75}, headers=ADMIN)
    assert (r.json()["map_x"], r.json()["map_y"]) == (0.25, 0.75)
    r = await client.patch(f"/api/admin/scenes/{a['id']}", json={"map_x": 1.5}, headers=ADMIN)
    assert r.status_code == 422


async def test_delete_tour(client):
    tour = await create_tour(client)
    await upload_scene(client, tour["id"])
    assert (await client.delete(f"/api/admin/tours/{tour['id']}", headers=ADMIN)).status_code == 204
    assert (await client.get(f"/api/tours/{tour['id']}", headers=ADMIN)).status_code == 404
