from __future__ import annotations

import pytest
from webtest import TestApp

from app.main import app


@pytest.fixture
def app_client():
    return TestApp(app)
