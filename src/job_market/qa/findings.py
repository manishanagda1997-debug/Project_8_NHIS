"""Shared result types for the quality gates."""

from __future__ import annotations

from dataclasses import dataclass, field

ERROR = "ERROR"
WARNING = "WARNING"
OK = "OK"


@dataclass(frozen=True)
class Finding:
    """One result of one check."""

    level: str
    check: str
    message: str
    location: str = ""

    def format(self) -> str:
        where = f" [{self.location}]" if self.location else ""
        return f"{self.level:<7} {self.check}{where}: {self.message}"


@dataclass
class Report:
    """A list of findings with a pass/fail verdict.

    The gate fails when any finding is an ERROR. In a strict report (strict
    mode, used by CI), every WARNING also fails the gate.
    """

    name: str
    findings: list[Finding] = field(default_factory=list)
    strict: bool = False

    def add(self, level: str, check: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(level, check, message, location))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARNING]

    @property
    def passed(self) -> bool:
        if self.strict:
            return not self.errors and not self.warnings
        return not self.errors

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        mode = ", strict: warnings fail" if self.strict else ""
        return f"{self.name}: {verdict} ({len(self.errors)} error(s), {len(self.warnings)} warning(s){mode})"

    def render(self, show_ok: bool = False) -> str:
        lines = [self.summary()]
        for finding in self.findings:
            if finding.level != OK or show_ok:
                lines.append("  " + finding.format())
        return "\n".join(lines)
