"""Fake OpenAI streaming client used to test the orchestrator without network calls."""
import json
from types import SimpleNamespace as NS
from typing import Any, Dict, List, Optional

from app.gateways.inventory_gateway import Listing


def text_turn(text: str) -> List[Any]:
    chunks = [NS(choices=[NS(delta=NS(content=piece, tool_calls=None))], usage=None) for piece in text.split(" ") if piece]
    for i, c in enumerate(chunks[:-1]):
        c.choices[0].delta.content += " "
    chunks.append(NS(choices=[], usage=NS(prompt_tokens=100, completion_tokens=20, prompt_tokens_details=NS(cached_tokens=0))))
    return chunks


def tool_turn(calls: List[Dict[str, Any]]) -> List[Any]:
    chunks = []
    for i, call in enumerate(calls):
        tc = NS(index=i, id=f"call_{i}", function=NS(name=call["name"], arguments=json.dumps(call.get("args", {}))))
        chunks.append(NS(choices=[NS(delta=NS(content=None, tool_calls=[tc]))], usage=None))
    chunks.append(NS(choices=[], usage=NS(prompt_tokens=100, completion_tokens=10, prompt_tokens_details=None)))
    return chunks


class _Stream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class FakeCompletions:
    def __init__(self, script: List[List[Any]], fail: bool = False):
        self.script = list(script)
        self.calls: List[Dict[str, Any]] = []
        self.fail = fail

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("provider down")
        if not kwargs.get("stream"):
            # Non-streaming calls (e.g. language-switch classifier) return a JSON verdict.
            content = json.dumps({"written_in": "en", "requests_language": None})
            return NS(choices=[NS(message=NS(content=content))])
        return _Stream(self.script.pop(0))


class FakeClient:
    def __init__(self, script: List[List[Any]], fail: bool = False):
        self.chat = NS(completions=FakeCompletions(script, fail))


def listing(**overrides) -> Listing:
    base = dict(id="offplan-1", source="live_offplan", title="Test Residence", developer="Emaar", city="Dubai", emirate="dubai",
                community="Jumeirah Village Circle", property_type="apartment", status="off-plan", beds_min=0, beds_max=3,
                price_from=700000, price_to=2400000, image_url=None, listing_url=None, amenities=[])
    base.update(overrides)
    return Listing(**base)
