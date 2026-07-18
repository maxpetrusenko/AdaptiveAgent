from types import SimpleNamespace

import pytest

import app.memory.cases as cases_module


class FakeDatabase:
    def __init__(self) -> None:
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        return None

    async def refresh(self, _value) -> None:
        return None


@pytest.mark.asyncio
async def test_failure_case_uses_shared_traced_model_factory(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeModel:
        async def ainvoke(self, _messages):
            return SimpleNamespace(
                content=(
                    '{"name":"math regression","input":"2+2",'
                    '"expected_output":"4","tags":["math"]}'
                )
            )

    def fake_build_chat_model(**kwargs):
        calls.append(kwargs)
        return FakeModel()

    monkeypatch.setattr(cases_module, "build_chat_model", fake_build_chat_model)
    db = FakeDatabase()

    await cases_module.failure_to_eval_case(
        db,
        {"input": "2+2", "expected": "4", "actual": "5"},
    )

    assert calls == [{"purpose": "judge", "streaming": False}]
