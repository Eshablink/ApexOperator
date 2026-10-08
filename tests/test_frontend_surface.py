from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_frontend_surface_exists_and_has_product_positioning():
    index = (FRONTEND / "index.html").read_text(encoding="utf-8")
    css = (FRONTEND / "assets" / "styles.css").read_text(encoding="utf-8")
    js = (FRONTEND / "assets" / "app.js").read_text(encoding="utf-8")

    assert "AI that <em>reasons.</em>" in index
    assert "Human approval" in index
    assert "TRUST BOUNDARY" in index
    assert "Operations Control Room" in index
    assert "dashboard/data" in js
    assert "Run governed workflow" in index
    assert "SAMPLE DATA" in index
    assert "Sign in as Finance Manager" in index
    assert "Simulate tampering" in index
    assert "Export JSON" in index
    assert "Task detail" in js or "operation detail" in js
    assert "Waking up the server" in js
    assert "Cache-Control" not in js
    assert (FRONTEND / "assets" / "favicon.svg").exists()
    assert (FRONTEND / "assets" / "og-image.svg").exists()
    assert len(css) > 10000
    assert len(js) > 7000


def test_frontend_assets_are_not_placeholder_shells():
    for path in (
        FRONTEND / "index.html",
        FRONTEND / "assets" / "styles.css",
        FRONTEND / "assets" / "app.js",
    ):
        assert path.exists()
        assert path.stat().st_size > 1000
