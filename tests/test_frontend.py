from fastapi.testclient import TestClient

from atlas.main import create_app


def test_frontend_assets_are_served_without_shadowing_api_routes():
    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert 'id="create-form"' in response.text
        for path, mime in [("/assets/app.js", "javascript"), ("/assets/style.css", "text/css")]:
            response = client.get(path)
            assert response.status_code == 200
            assert mime in response.headers["content-type"]
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404
