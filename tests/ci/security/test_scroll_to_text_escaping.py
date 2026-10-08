"""Tests for ScrollToTextEvent XPath and Runtime.evaluate escaping."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from browser_use.browser.events import ScrollToTextEvent
from browser_use.browser.watchdogs.default_action_watchdog import DefaultActionWatchdog


class _RecordingDOM:
	def __init__(self) -> None:
		self.queries: list[str] = []

	async def enable(self, session_id: str | None = None) -> None:
		return None

	async def getDocument(self, params: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
		return {'root': {'nodeId': 1}}

	async def performSearch(self, params: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
		self.queries.append(params['query'])
		return {'searchId': 's1', 'resultCount': 0}

	async def discardSearchResults(self, params: dict[str, Any], session_id: str | None = None) -> None:
		return None


class _RecordingRuntime:
	def __init__(self) -> None:
		self.expressions: list[str] = []

	async def evaluate(self, params: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
		self.expressions.append(params['expression'])
		return {'result': {'value': True}}


class _StubWatchdog:
	def __init__(self) -> None:
		self.dom = _RecordingDOM()
		self.runtime = _RecordingRuntime()
		self.logger = logging.getLogger('test_scroll_to_text_escaping')
		send = type('Send', (), {'DOM': self.dom, 'Runtime': self.runtime})()
		cdp_client = type('CDPClient', (), {'send': send})()
		cdp_session = type('CDPSession', (), {'cdp_client': cdp_client, 'session_id': 'sid-1'})()

		async def get_or_create_cdp_session():
			return cdp_session

		self.browser_session = type(
			'BrowserSessionStub',
			(),
			{'get_or_create_cdp_session': get_or_create_cdp_session, 'logger': self.logger},
		)()


@pytest.mark.parametrize(
	('text', 'expected_xpath_literal'),
	[
		('simple text', '"simple text"'),
		('"); alert(1);//', '\'"); alert(1);//\''),
		("O'Reilly", '"O\'Reilly"'),
		('say "it\'s ok"', 'concat("say ", \'"\', "it\'s ok", \'"\', "")'),
		('line1\nline2\\end', '"line1\nline2\\end"'),
	],
)
async def test_scroll_to_text_escapes_xpath_and_runtime_evaluate(
	text: str,
	expected_xpath_literal: str,
) -> None:
	stub = _StubWatchdog()
	event = ScrollToTextEvent(text=text)

	await DefaultActionWatchdog.on_ScrollToTextEvent(stub, event)  # type: ignore[arg-type]

	assert stub.dom.queries == [
		f'//*[contains(text(), {expected_xpath_literal})]',
		f'//*[contains(., {expected_xpath_literal})]',
		f'//*[@*[contains(., {expected_xpath_literal})]]',
	]
	assert len(stub.runtime.expressions) == 1
	expression = stub.runtime.expressions[0]
	assert f'const searchText = {json.dumps(text)};' in expression
