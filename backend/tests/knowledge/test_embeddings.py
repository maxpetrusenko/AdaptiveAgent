import httpx
import pytest

from app.knowledge.embeddings import (
    DeterministicTestEmbedder,
    OpenAICompatibleEmbeddingProvider,
)


@pytest.mark.asyncio
async def test_deterministic_embedder_is_repeatable_normalized_and_fingerprinted():
    embedder = DeterministicTestEmbedder(dimensions=16, revision="fixture-v1")

    first = (await embedder.embed(["alpha beta"]))[0]
    second = (await embedder.embed(["alpha beta"]))[0]
    different = (await embedder.embed(["gamma delta"]))[0]

    assert first == second
    assert first != different
    assert sum(value * value for value in first) == pytest.approx(1.0)
    assert embedder.identity.provider == "deterministic-test"
    assert embedder.identity.dimensions == 16
    assert len(embedder.identity.fingerprint) == 64


@pytest.mark.asyncio
async def test_openai_compatible_provider_uses_real_embeddings_contract():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ],
                "model": "semantic-v1",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="https://embedding.example/v1",
            api_key="test-key",
            model="semantic-v1",
            dimensions=3,
            revision="2026-07-18",
            client=client,
        )
        vectors = await provider.embed(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert requests[0].url == "https://embedding.example/v1/embeddings"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert b'"dimensions":3' in requests[0].content
    assert provider.identity.fingerprint


@pytest.mark.asyncio
async def test_provider_rejects_wrong_dimensions_fail_closed():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="https://embedding.example/v1",
            api_key="test-key",
            model="semantic-v1",
            dimensions=3,
            client=client,
        )
        with pytest.raises(ValueError, match="dimension"):
            await provider.embed(["first"])
