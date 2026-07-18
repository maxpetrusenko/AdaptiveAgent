import sys
from types import ModuleType, SimpleNamespace

from app.observability.langfuse import langchain_callbacks


def test_langchain_callbacks_are_disabled_without_credentials() -> None:
    config = SimpleNamespace(
        langfuse_public_key="",
        langfuse_secret_key="",
        langfuse_base_url="https://cloud.langfuse.com",
    )

    assert langchain_callbacks(config) == []


def test_langchain_callbacks_create_configured_handler(monkeypatch) -> None:
    handler_args: dict[str, str] = {}
    client_args: dict[str, object] = {}

    class FakeCallbackHandler:
        def __init__(self, **kwargs: str) -> None:
            handler_args.update(kwargs)

    class FakeLangfuse:
        def __init__(self, **kwargs: object) -> None:
            client_args.update(kwargs)

    fake_langfuse = ModuleType("langfuse")
    fake_langfuse.Langfuse = FakeLangfuse  # type: ignore[attr-defined]
    fake_langchain = ModuleType("langfuse.langchain")
    fake_langchain.CallbackHandler = FakeCallbackHandler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setitem(sys.modules, "langfuse.langchain", fake_langchain)
    config = SimpleNamespace(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="https://langfuse.example.com",
    )

    callbacks = langchain_callbacks(config)

    assert len(callbacks) == 1
    assert handler_args == {"public_key": "pk-test"}
    assert client_args["public_key"] == "pk-test"
    assert client_args["secret_key"] == "sk-test"
    assert client_args["base_url"] == "https://langfuse.example.com"
    assert callable(client_args["mask_otel_spans"])
