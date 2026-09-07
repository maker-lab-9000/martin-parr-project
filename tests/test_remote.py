from __future__ import annotations

import http.client
import io
import json
import socket
import threading
import time
import uuid
from dataclasses import dataclass

import numpy as np
import pytest
from PIL import Image

from parr.capture.controller import CaptureController
from parr.capture.remote import RemoteCaptureServer
from parr.capture.thumbnail import fitted_jpeg


@dataclass
class SavedCapture:
    parr: object
    # The real CaptureResult also carries `original`, the camera's own frame.
    # Leaving it out of the double meant no test could tell which of the two
    # the API serves, so a swap would have been invisible.
    original: object = None


class BlockingSession:
    def __init__(self, result: object | None = None):
        self.camera = type("Camera", (), {"close": lambda _self: None})()
        self.started = threading.Event()
        self.release = threading.Event()
        self.result = result

    def capture(self):
        self.started.set()
        self.release.wait(timeout=2)
        return self.result


@pytest.fixture
def remote(tmp_path):
    image = tmp_path / "graded.jpg"
    Image.fromarray(np.full((100, 400, 3), (200, 30, 20), dtype=np.uint8)).save(image)
    session = BlockingSession(SavedCapture(image))
    controller = CaptureController(session)
    server = RemoteCaptureServer(controller, "secret-token", ("127.0.0.1", 0))
    server.start()
    try:
        yield server, session
    finally:
        session.release.set()
        server.close()
        controller.close()


def _request(server, method, target, body=None, token="secret-token"):
    conn = http.client.HTTPConnection(*server.address, timeout=2)
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    conn.request(method, target, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    headers = dict(response.getheaders())
    conn.close()
    return response.status, headers, data


def _json(server, method, target, body=None, token="secret-token"):
    status, headers, data = _request(server, method, target, body, token)
    return status, headers, json.loads(data.decode())


def test_api_rejects_missing_and_wrong_bearer_tokens(remote):
    """Removing authentication would expose a camera trigger to the local network."""
    server, _ = remote
    assert _request(server, "GET", "/v1/status", token=None)[0] == 401
    assert _request(server, "GET", "/v1/status", token="not-the-token")[0] == 401
    assert _json(server, "GET", "/v1/status")[0] == 200


def test_api_rejects_a_non_ascii_bearer_header_without_losing_the_handler(remote):
    """A malformed raw header must be unauthorized, not crash its request thread."""
    server, _ = remote
    request = (
        b"GET /v1/status HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Authorization: Bearer \xff\r\n"
        b"Connection: close\r\n\r\n"
    )
    with socket.create_connection(server.address, timeout=2) as connection:
        connection.sendall(request)
        response = connection.recv(4096)

    assert response.startswith(b"HTTP/1.1 401")
    assert _json(server, "GET", "/v1/status")[0] == 200


def test_post_is_uuid_validated_bounded_idempotent_and_busy(remote):
    """A malformed, repeated, or concurrent press must not trigger extra captures."""
    server, session = remote
    assert _json(server, "POST", "/v1/captures", b"{} ")[0] == 400
    assert _json(server, "POST", "/v1/captures", b'{"request_id":"not-a-uuid"}')[0] == 400
    assert _request(server, "POST", "/v1/captures", b"x" * 9_000)[0] == 413

    first = str(uuid.uuid4())
    first_body = json.dumps({"request_id": first}).encode()
    status, _, accepted = _json(server, "POST", "/v1/captures", first_body)
    assert status == 202
    assert accepted["id"] == first
    assert session.started.wait(timeout=1)

    status, _, duplicate = _json(server, "POST", "/v1/captures", first_body)
    assert status == 202
    assert duplicate["id"] == first
    assert duplicate["state"] in {"queued", "processing"}
    another_body = json.dumps({"request_id": str(uuid.uuid4())}).encode()
    assert _json(server, "POST", "/v1/captures", another_body)[0] == 409


def test_status_and_capture_lookup_are_scoped_to_this_server_lifetime(remote):
    """Looking up arbitrary paths or controller history would disclose stale files."""
    server, session = remote
    instance = _json(server, "GET", "/v1/status")[2]["instance_id"]
    assert uuid.UUID(instance)
    assert _json(server, "GET", "/v1/captures/not-a-job")[0] == 404
    assert _json(server, "GET", "/v1/captures/%2Fetc%2Fpasswd")[0] == 404

    request_id = str(uuid.uuid4())
    _json(server, "POST", "/v1/captures", json.dumps({"request_id": request_id}).encode())
    assert session.started.wait(timeout=1)
    status = _json(server, "GET", "/v1/status")[2]
    assert status["active_capture_id"] == request_id
    session.release.set()
    for _ in range(100):
        result = _json(server, "GET", f"/v1/captures/{request_id}")[2]
        if result["state"] == "complete":
            break
        time.sleep(0.01)
    assert result["state"] == "complete"
    assert result["image_url"] == f"/v1/captures/{request_id}/image.jpg"


def test_completed_job_serves_only_its_own_fitted_image(tmp_path):
    """A global latest-image lookup could return a different customer's photo."""
    image = tmp_path / "graded.jpg"
    Image.fromarray(np.full((100, 400, 3), (200, 30, 20), dtype=np.uint8)).save(image)
    session = BlockingSession(SavedCapture(image))
    controller = CaptureController(session)
    server = RemoteCaptureServer(controller, "secret-token", ("127.0.0.1", 0))
    server.start()
    try:
        request_id = str(uuid.uuid4())
        _json(server, "POST", "/v1/captures", json.dumps({"request_id": request_id}).encode())
        assert session.started.wait(timeout=1)
        assert _request(server, "GET", f"/v1/captures/{request_id}/image.jpg")[0] == 409
        session.release.set()
        for _ in range(100):
            status, headers, data = _request(server, "GET", f"/v1/captures/{request_id}/image.jpg")
            if status == 200:
                break
            time.sleep(0.01)
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert data[:2] == b"\xff\xd8"
        assert len(data) <= 64 * 1024
    finally:
        session.release.set()
        server.close()
        controller.close()


def test_expired_job_is_not_reused_after_the_bounded_registry_forgets_it():
    """Retrying a forgotten press could otherwise expose an uncertain old outcome."""

    class ImmediateSession:
        camera = type("Camera", (), {"close": lambda _self: None})()

        def capture(self):
            return SavedCapture(None)

    controller = CaptureController(ImmediateSession())
    server = RemoteCaptureServer(controller, "secret-token", ("127.0.0.1", 0))
    server.start()
    try:
        request_ids = [str(uuid.uuid4()) for _ in range(101)]
        for request_id in request_ids:
            body = json.dumps({"request_id": request_id}).encode()
            assert _json(server, "POST", "/v1/captures", body)[0] == 202
            for _ in range(100):
                job = controller.status(request_id)
                if job is not None and job.state == "complete":
                    break
                time.sleep(0.001)
            else:
                raise AssertionError("immediate job did not complete")

        assert _json(server, "GET", f"/v1/captures/{request_ids[0]}")[0] == 404
        first_body = json.dumps({"request_id": request_ids[0]}).encode()
        assert _json(server, "POST", "/v1/captures", first_body)[0] == 404
    finally:
        server.close()
        controller.close()


def test_the_api_serves_the_graded_image_and_never_the_camera_original(tmp_path):
    """The Stick shows what this endpoint returns, so it must be the grade.

    `SavedCapture` used to carry only `parr`, so every existing test passed a
    single file as both and could not distinguish them: swapping `parr` for
    `original` in the handler would have gone unnoticed.
    """
    graded = tmp_path / "shot_parr.jpg"
    original = tmp_path / "shot_ungraded.jpg"
    Image.fromarray(np.full((135, 240, 3), (210, 90, 40), dtype=np.uint8)).save(graded)
    Image.fromarray(np.full((135, 240, 3), (120, 120, 120), dtype=np.uint8)).save(original)

    session = BlockingSession(SavedCapture(graded, original))
    controller = CaptureController(session)
    server = RemoteCaptureServer(controller, "secret-token", ("127.0.0.1", 0))
    server.start()
    try:
        request_id = str(uuid.uuid4())
        _json(server, "POST", "/v1/captures", json.dumps({"request_id": request_id}).encode())
        assert session.started.wait(timeout=1)
        session.release.set()
        status, data = 0, b""
        for _ in range(100):
            status, _headers, data = _request(server, "GET", f"/v1/captures/{request_id}/image.jpg")
            if status == 200:
                break
            time.sleep(0.01)
        assert status == 200
        assert data == fitted_jpeg(graded), "served bytes are not the graded image"
        assert data != fitted_jpeg(original)
        # And the served frame is visibly the warm one, not neutral grey.
        served = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=np.int16)
        assert served[:, :, 0].mean() - served[:, :, 2].mean() > 40
    finally:
        session.release.set()
        server.close()
        controller.close()
