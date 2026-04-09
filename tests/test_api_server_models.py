from smart_router.entrypoints.serve import api_server


def test_model_source_urls_round_trip(monkeypatch):
    monkeypatch.delenv(api_server.MODEL_SOURCE_URLS_ENV, raising=False)

    api_server._dump_model_source_urls(
        ["http://prefill-a", "http://shared"],
        ["http://shared", "http://decode-b"],
    )

    assert api_server._load_model_source_urls() == [
        "http://prefill-a",
        "http://shared",
        "http://decode-b",
    ]


def test_load_model_source_urls_handles_invalid_payload(monkeypatch):
    monkeypatch.setenv(api_server.MODEL_SOURCE_URLS_ENV, '{"bad": true}')
    assert api_server._load_model_source_urls() == []

    monkeypatch.setenv(api_server.MODEL_SOURCE_URLS_ENV, "not-json")
    assert api_server._load_model_source_urls() == []
