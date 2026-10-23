"""Reddit SDK attempts participate in the HTTP request's provider budget."""
import pytest
from unittest.mock import AsyncMock

import api_security
from app.pipeline import ingestion


@pytest.mark.asyncio
async def test_reddit_sdk_attempts_cannot_bypass_call_budget(monkeypatch):
    request = AsyncMock(return_value=object())
    monkeypatch.setattr(ingestion.Requestor, "request", request)
    # The underlying transport is stubbed, so no SDK session is created.
    requestor = object.__new__(ingestion._BudgetedRedditRequestor)
    token = api_security._work_budget.set(api_security.WorkBudget(remaining=2))
    try:
        await requestor.request("POST", "https://www.reddit.com/api/v1/access_token")
        await requestor.request("GET", "https://oauth.reddit.com/r/news/hot")
        with pytest.raises(api_security.WorkLimitExceeded):
            await requestor.request("GET", "https://oauth.reddit.com/r/news/hot")
        assert request.await_count == 2
    finally:
        api_security._work_budget.reset(token)


@pytest.mark.asyncio
async def test_reddit_expired_deadline_denies_io(monkeypatch):
    request = AsyncMock()
    monkeypatch.setattr(ingestion.Requestor, "request", request)
    requestor = object.__new__(ingestion._BudgetedRedditRequestor)
    token = api_security._work_budget.set(api_security.WorkBudget(deadline=0))
    try:
        with pytest.raises(api_security.WorkLimitExceeded):
            await requestor.request("GET", "https://oauth.reddit.com/r/news/hot")
        request.assert_not_awaited()
    finally:
        api_security._work_budget.reset(token)
