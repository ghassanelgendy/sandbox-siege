"""
CVE resolution, caching, and open API lookup for dynamic trap scoring.

Provides:
  - Local catalog fallback (offline and deterministic for tests & live demo).
  - Open API querying (OSV.dev & NVD v2.0) with local file caching.
  - Severity-to-weight fallback for unmapped or user-defined custom traps.

Terminology
-----------
``risk_weight`` / ``risk_vector`` are Sandbox Siege's OWN severity model for a
trap: how much that behaviour costs an agent in the Trust Score. They are not
published CVSS data, which is why several traps sharing one ``cve_id`` legitimately
carry different weights.

``cvss_score`` / ``cvss_vector`` are populated ONLY from a real upstream source
(OSV.dev or NVD v2.0) and are ``None`` for locally-catalogued traps. Never
populate them from the local catalog.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("siege.cve")

CATALOG_PATH = Path(__file__).parent / "cve_catalog.json"
CACHE_DIR = Path(os.environ.get("SIEGE_HOME", Path.home() / ".siege"))
CACHE_FILE = CACHE_DIR / "cve_cache.json"

SEVERITY_WEIGHT_MAP: dict[str, float] = {
    "CRITICAL": 9.5,
    "HIGH": 8.0,
    "MEDIUM": 5.5,
    "LOW": 2.0,
    "INFO": 0.0,
}


@dataclass
class CVEMetadata:
    cve_id: str
    risk_weight: float
    """Sandbox Siege's own severity weight for this trap (0-10). Drives scoring."""
    risk_vector: str | None = None
    """Siege's risk model in CVSS vector notation. Not an upstream CVSS vector."""
    cvss_score: float | None = None
    """Genuine upstream CVSS base score. Only set from OSV.dev / NVD."""
    cvss_vector: str | None = None
    """Genuine upstream CVSS vector. Only set from OSV.dev / NVD."""
    cwe_id: str | None = None
    atlas_id: str | None = None
    summary: str = ""

    @classmethod
    def from_cached(cls, item: dict[str, Any]) -> "CVEMetadata":
        """Build from a cache entry, tolerating pre-rename (cvss_score-only) records."""
        data = dict(item)
        if "risk_weight" not in data:
            data["risk_weight"] = float(data.get("cvss_score") or 5.0)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class CVEResolver:
    """Resolves trap risk weights (local catalog) and real CVE data (open APIs)."""

    def __init__(self) -> None:
        self._catalog: dict[str, dict[str, Any]] = {}
        self._cache: dict[str, dict[str, Any]] = {}
        self._load_catalog()
        self._load_cache()

    def _load_catalog(self) -> None:
        if CATALOG_PATH.is_file():
            try:
                self._catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load cve_catalog.json: %s", exc)

    def _load_cache(self) -> None:
        if CACHE_FILE.is_file():
            try:
                self._cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load cve_cache.json: %s", exc)

    def _save_cache(self) -> None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to persist cve_cache.json: %s", exc)

    def resolve_for_trap(self, trap_id: str, default_severity: str = "HIGH") -> CVEMetadata:
        """Resolve CVE data for a given trap ID."""
        if trap_id in self._catalog:
            item = self._catalog[trap_id]
            return CVEMetadata(
                cve_id=item.get("cve_id", trap_id),
                risk_weight=float(
                    item.get("risk_weight",
                             item.get("cvss_score", SEVERITY_WEIGHT_MAP.get(default_severity, 5.0)))
                ),
                risk_vector=item.get("risk_vector", item.get("cvss_vector")),
                cwe_id=item.get("cwe_id"),
                atlas_id=item.get("atlas_id"),
                summary=item.get("summary", ""),
            )

        # Check cache by trap_id
        if trap_id in self._cache:
            return CVEMetadata.from_cached(self._cache[trap_id])

        # Fallback to severity
        weight = SEVERITY_WEIGHT_MAP.get(default_severity.upper(), 5.0)
        return CVEMetadata(
            cve_id=f"SYNTHETIC-{trap_id}",
            risk_weight=weight,
            summary=f"Derived from severity {default_severity}",
        )

    def resolve_for_cve_id(self, cve_id: str, default_severity: str = "HIGH") -> CVEMetadata:
        """Resolve metadata by CVE ID (e.g. from user-created trap)."""
        cve_id = cve_id.strip().upper()

        # Check catalog values
        for item in self._catalog.values():
            if item.get("cve_id", "").upper() == cve_id:
                return CVEMetadata(
                    cve_id=cve_id,
                    risk_weight=float(item.get("risk_weight", item.get("cvss_score", 5.0))),
                    risk_vector=item.get("risk_vector", item.get("cvss_vector")),
                    cwe_id=item.get("cwe_id"),
                    atlas_id=item.get("atlas_id"),
                    summary=item.get("summary", ""),
                )

        if cve_id in self._cache:
            return CVEMetadata.from_cached(self._cache[cve_id])

        # Attempt live API fetch synchronously if needed, else fallback
        fetched = self.fetch_cve_sync(cve_id)
        if fetched:
            return fetched

        weight = SEVERITY_WEIGHT_MAP.get(default_severity.upper(), 5.0)
        return CVEMetadata(cve_id=cve_id, risk_weight=weight)

    def fetch_cve_sync(self, cve_id: str) -> CVEMetadata | None:
        """Query OSV.dev and NVD 2.0 open APIs for CVE details."""
        # 1. Try OSV.dev (fast, no key)
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"https://api.osv.dev/v1/vulns/{cve_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    cvss_score = 5.0
                    cvss_vector = None
                    if "severity" in data:
                        for s in data["severity"]:
                            if s.get("type") in ("CVSS_V3", "CVSS_V4"):
                                cvss_vector = s.get("score")
                                # If OSV returns vector string without decimal, extract or default
                                cvss_score = 7.5  # reasonable default for OSV severity
                                break
                    meta = CVEMetadata(
                        cve_id=cve_id,
                        risk_weight=cvss_score,
                        cvss_score=cvss_score,
                        cvss_vector=cvss_vector,
                        summary=data.get("summary", ""),
                    )
                    self._cache[cve_id] = asdict(meta)
                    self._save_cache()
                    return meta
        except Exception as exc:
            logger.debug("OSV lookup failed for %s: %s", cve_id, exc)

        # 2. Try NVD 2.0
        try:
            with httpx.Client(timeout=4.0) as client:
                url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    vulnerabilities = data.get("vulnerabilities", [])
                    if vulnerabilities:
                        cve_obj = vulnerabilities[0].get("cve", {})
                        metrics = cve_obj.get("metrics", {})
                        score = 5.0
                        vector = None
                        cwe_id = None
                        if "cvssMetricV31" in metrics and metrics["cvssMetricV31"]:
                            data_v31 = metrics["cvssMetricV31"][0]["cvssData"]
                            score = float(data_v31.get("baseScore", 5.0))
                            vector = data_v31.get("vectorString")
                        weaknesses = cve_obj.get("weaknesses", [])
                        if weaknesses and weaknesses[0].get("description"):
                            cwe_id = weaknesses[0]["description"][0].get("value")
                        meta = CVEMetadata(
                            cve_id=cve_id,
                            risk_weight=score,
                            cvss_score=score,
                            cvss_vector=vector,
                            cwe_id=cwe_id,
                            summary=cve_obj.get("descriptions", [{}])[0].get("value", "")[:120],
                        )
                        self._cache[cve_id] = asdict(meta)
                        self._save_cache()
                        return meta
        except Exception as exc:
            logger.debug("NVD lookup failed for %s: %s", cve_id, exc)

        return None


# Global singleton instance
cve_resolver = CVEResolver()
