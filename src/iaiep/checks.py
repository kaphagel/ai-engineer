"""Results of deterministic engineering checks (spec §11, §12.7, §14)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    # Passed, but against a criterion that is not yet approved (for example a placeholder value).
    PASS_UNAPPROVED = "pass_unapproved_criterion"


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: CheckStatus
    detail: str
    source: str  # what performed the check, for example "worker", "calculation", "pdf"

    @property
    def failed(self) -> bool:
        return self.status is CheckStatus.FAIL
