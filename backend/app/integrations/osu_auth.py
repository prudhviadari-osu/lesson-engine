"""OSU credential cross-verification + two-factor flow (mockable).

Real flow (VM): Playwright drives the OSU login page, cross-verifies the
name.# exists, then triggers BuckeyePass / Duo two-factor. Offline we
simulate: any name.# that looks valid 'exists', and the 2FA code is 000000.
"""
from __future__ import annotations

import logging
import re

from ..core.config import settings

logger = logging.getLogger("learnpp.osuauth")

_NAME_DOT_NUMBER = re.compile(r"^[a-z]+\.\d+$", re.IGNORECASE)
MOCK_2FA_CODE = "000000"


class OSUAuth:
    def __init__(self) -> None:
        self.use_mock = settings.USE_MOCK_INTEGRATIONS

    def verify_exists(self, name_dot_number: str | None) -> bool:
        """Cross-verify the OSU identity exists."""
        if not name_dot_number:
            return False
        if self.use_mock:
            return bool(_NAME_DOT_NUMBER.match(name_dot_number.strip()))
        return self._real_verify(name_dot_number)  # pragma: no cover

    def start_two_factor(self, name_dot_number: str) -> dict:
        """Kick off 2FA; returns a challenge descriptor."""
        if self.use_mock:
            return {"method": "mock", "message": f"Enter code {MOCK_2FA_CODE} to continue."}
        return self._real_start_2fa(name_dot_number)  # pragma: no cover

    def verify_two_factor(self, name_dot_number: str, code: str) -> bool:
        if self.use_mock:
            return code == MOCK_2FA_CODE
        return self._real_verify_2fa(name_dot_number, code)  # pragma: no cover

    # -- real implementations (VM) -----------------------------------------
    def _real_verify(self, name_dot_number: str) -> bool:  # pragma: no cover
        raise NotImplementedError("Wire up OSU IdP lookup on the VM.")

    def _real_start_2fa(self, name_dot_number: str) -> dict:  # pragma: no cover
        raise NotImplementedError("Wire up BuckeyePass/Duo push on the VM.")

    def _real_verify_2fa(self, name_dot_number: str, code: str) -> bool:  # pragma: no cover
        raise NotImplementedError("Wire up BuckeyePass/Duo verification on the VM.")
