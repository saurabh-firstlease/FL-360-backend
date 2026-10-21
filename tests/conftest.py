import io
import os
import tempfile

# Configure before the app is imported.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://localhost:5432/fl_tours_test"
)
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["DB_NULLPOOL"] = "1"
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="fl-tours-media-")

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = {"Authorization": "Bearer test-admin-token"}
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def make_image(width: int, height: int, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 140, 160)).save(buf, fmt)
    return buf.getvalue()
