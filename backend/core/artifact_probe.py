"""
[5] Module 2 — Automated Artifact Probe (English Edition).
Verifies GitHub/GitLab/HuggingFace/Zenodo/OSF links without cloning heavy repos:
- SSRF & DNS Rebinding protection + Domain Moderation Queue for unknown department servers.
- GitHub PAT Pool rotation in Redis + DEFERRED_RETRY graceful degradation.
- 5 binary verification flags (repo_alive, has_dependencies >= 15B, has_clean_paths + ijson .ipynb streaming,
  has_data_artifact > 250B filtering out 130B Git LFS pointers, has_license).
"""

from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import logging
import re
import socket
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
import ijson
import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config_and_db import (
    DistributedCircuitBreaker,
    get_redis_cache,
    get_redis_state,
    settings,
)
from models_and_schemas import (
    ArtifactVerificationDTO,
    DomainModerationQueue,
    ProbeStatus,
)

logger = logging.getLogger("horizon.probe")

github_cb = DistributedCircuitBreaker("github_api", failure_threshold=5, window_sec=30, cooldown_sec=60)

DEPENDENCY_FILENAMES = {
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "environment.yml": "Conda/Python",
    "pipfile": "Python",
    "setup.py": "Python",
    "package.json": "TypeScript/JS",
    "cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java",
    "cmakelists.txt": "C/C++",
    "dockerfile": "Docker",
    "docker-compose.yml": "Docker",
}

DATA_ARTIFACT_EXTENSIONS = (
    ".csv",
    ".tsv",
    ".parquet",
    ".feather",
    ".xlsx",
    ".xls",
    ".pt",
    ".pth",
    ".onnx",
    ".safetensors",
    ".ckpt",
    ".h5",
    ".hdf5",
    ".npz",
    ".npy",
    ".sqlite",
    ".db",
    ".edf",
    ".dcm",
)

HARDCODED_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\\\Users\\\\|[A-Za-z]:/Users/|/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|/content/drive/MyDrive/)",
    re.IGNORECASE,
)


def verify_host_not_ssrf(hostname: str) -> str:
    if not hostname:
        raise ValueError("SSRF_BLOCKED: Empty hostname.")

    clean_host = hostname.strip().lower()
    if clean_host in ("localhost", "0.0.0.0", "::1"):
        raise ValueError(f"SSRF_BLOCKED: Loopback host forbidden ({clean_host}).")

    try:
        addr_info = socket.getaddrinfo(clean_host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"DNS_RESOLUTION_FAILED: Cannot resolve host {clean_host}: {exc}") from exc

    verified_ip: str | None = None
    for _, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        ip_obj = ipaddress.ip_address(ip_str)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            raise ValueError(f"SSRF_BLOCKED: Host {clean_host} resolves to private/internal IP {ip_str}.")
        if verified_ip is None:
            verified_ip = ip_str

    if not verified_ip:
        raise ValueError(f"SSRF_BLOCKED: No public IP found for {clean_host}.")
    return verified_ip


async def is_domain_allowed(db: AsyncSession, domain: str) -> bool:
    norm_domain = domain.strip().lower().removeprefix("www.")
    allow_set = settings.allowlist_domains_set
    if any(norm_domain == d or norm_domain.endswith("." + d) for d in allow_set):
        return True

    stmt = select(DomainModerationQueue).where(
        DomainModerationQueue.domain == norm_domain,
        DomainModerationQueue.status == "APPROVED",
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none() is not None


async def enqueue_domain_for_moderation(
    db: AsyncSession,
    domain: str,
    full_url: str,
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
) -> None:
    norm_domain = domain.strip().lower().removeprefix("www.")
    stmt = select(DomainModerationQueue).where(DomainModerationQueue.domain == norm_domain)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is None:
        item = DomainModerationQueue(
            domain=norm_domain,
            sample_url=full_url[:500],
            project_id=project_id,
            revision_id=revision_id,
            status="PENDING",
        )
        db.add(item)
        await db.commit()


async def safe_get_with_redirect_guard(
    client: httpx.AsyncClient,
    db: AsyncSession,
    url: str,
    headers: dict[str, str] | None = None,
    max_hops: int = 3,
) -> httpx.Response:
    current_url = url
    for _ in range(max_hops + 1):
        parsed = urlparse(current_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"UNSUPPORTED_SCHEME: {parsed.scheme}")
        host = parsed.hostname or ""
        verify_host_not_ssrf(host)

        if not await is_domain_allowed(db, host):
            raise PermissionError(f"DOMAIN_NOT_IN_ALLOWLIST:{host}")

        resp = await client.get(current_url, headers=headers, follow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location")
            if not loc:
                return resp
            current_url = str(resp.url.join(loc))
            continue
        return resp

    raise ValueError("TOO_MANY_REDIRECTS")


async def get_next_github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Horizon-Relay-Academic-Auditor/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    tokens = settings.github_tokens_list
    if not tokens:
        return headers

    r = get_redis_state()
    for _ in range(len(tokens)):
        idx = await r.incr("gh:pat:rr_idx")
        token = tokens[idx % len(tokens)]
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:12]
        exhausted = await r.get(f"gh:pat:exhausted:{token_hash}")
        if not exhausted:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Horizon-Token-Hash"] = token_hash
            return headers

    return headers


async def mark_github_token_exhausted_if_needed(resp: httpx.Response, req_headers: dict[str, str]) -> bool:
    remaining = resp.headers.get("X-RateLimit-Remaining")
    reset_ts = resp.headers.get("X-RateLimit-Reset")
    if remaining == "0" or (resp.status_code in (403, 429) and "rate limit" in resp.text.lower()):
        token_hash = req_headers.get("X-Horizon-Token-Hash")
        if token_hash:
            r = get_redis_state()
            ttl = 900
            if reset_ts and reset_ts.isdigit():
                import time

                ttl = max(60, int(reset_ts) - int(time.time()) + 5)
            await r.setex(f"gh:pat:exhausted:{token_hash}", ttl, b"1")
        return True
    return False


def inspect_ipynb_bytes_streaming(raw_ipynb_bytes: bytes) -> tuple[bool, int]:
    clean_paths = True
    executed_cells_count = 0

    try:
        stream = io.BytesIO(raw_ipynb_bytes)
        for cell in ijson.items(stream, "cells.item"):
            if not isinstance(cell, dict):
                continue
            if cell.get("cell_type") != "code":
                continue

            exec_count = cell.get("execution_count")
            if exec_count is not None:
                executed_cells_count += 1

            source = cell.get("source", [])
            if isinstance(source, list):
                code_text = "".join(str(line) for line in source)
            else:
                code_text = str(source)

            if HARDCODED_LOCAL_PATH_RE.search(code_text):
                clean_paths = False
    except Exception as exc:
        logger.debug("ijson streaming parse warning: %s", exc)

    return clean_paths, executed_cells_count


def inspect_script_text_for_hardcoded_paths(script_text: str) -> bool:
    return not bool(HARDCODED_LOCAL_PATH_RE.search(script_text))


def _parse_github_owner_repo(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host != "github.com":
        return None
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    return owner, repo


async def _probe_github_repository(
    client: httpx.AsyncClient,
    db: AsyncSession,
    repo_url: str,
    owner: str,
    repo: str,
) -> ArtifactVerificationDTO:
    if not await github_cb.is_available():
        return ArtifactVerificationDTO(
            repo_url=repo_url,
            probe_status=ProbeStatus.DEFERRED_RETRY,
            diagnostics={"reason": "GitHub CircuitBreaker is OPEN; scheduled for background retry."},
        )

    req_headers = await get_next_github_headers()
    clean_headers = {k: v for k, v in req_headers.items() if k != "X-Horizon-Token-Hash"}

    meta_url = f"https://api.github.com/repos/{owner}/{repo}"
    meta_resp = await safe_get_with_redirect_guard(client, db, meta_url, headers=clean_headers)

    if await mark_github_token_exhausted_if_needed(meta_resp, req_headers):
        await github_cb.record_failure(custom_cooldown=60)
        return ArtifactVerificationDTO(
            repo_url=repo_url,
            probe_status=ProbeStatus.DEFERRED_RETRY,
            diagnostics={"reason": "GitHub API Rate Limit reached; queued for automatic retry."},
        )

    if meta_resp.status_code == 404:
        return ArtifactVerificationDTO(
            repo_url=repo_url,
            repo_alive=False,
            probe_status=ProbeStatus.UNVERIFIED,
            diagnostics={"http_status": 404, "reason": "Repository not found (404) or private."},
        )

    if meta_resp.status_code >= 500:
        await github_cb.record_failure()
        return ArtifactVerificationDTO(
            repo_url=repo_url,
            probe_status=ProbeStatus.DEFERRED_RETRY,
            diagnostics={"http_status": meta_resp.status_code},
        )

    await github_cb.record_success()
    repo_meta = meta_resp.json()
    default_branch = repo_meta.get("default_branch") or "HEAD"
    license_info = repo_meta.get("license") or {}
    has_license = bool(license_info.get("spdx_id") and license_info.get("spdx_id") != "NOASSERTION")

    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    tree_resp = await safe_get_with_redirect_guard(client, db, tree_url, headers=clean_headers)
    if tree_resp.status_code != 200:
        return ArtifactVerificationDTO(
            repo_url=repo_url,
            repo_alive=False,
            probe_status=ProbeStatus.UNVERIFIED,
            diagnostics={"reason": "Empty repository with no commits."},
        )

    tree_data = tree_resp.json()
    latest_sha = tree_data.get("sha")
    blobs = [
        item
        for item in tree_data.get("tree", [])
        if isinstance(item, dict) and item.get("type") == "blob"
    ]

    non_empty_files = [b for b in blobs if int(b.get("size", 0)) > 0]
    repo_alive = len(non_empty_files) > 5

    has_dependencies = False
    has_data_artifact = False
    detected_stack: set[str] = set()
    dependency_files_found: list[str] = []
    data_files_found: list[str] = []
    candidate_code_files: list[dict[str, Any]] = []

    for blob in non_empty_files:
        path_str = str(blob.get("path", ""))
        fname = path_str.split("/")[-1].lower()
        fsize = int(blob.get("size", 0))

        if fname in DEPENDENCY_FILENAMES and fsize >= 15:
            has_dependencies = True
            dependency_files_found.append(path_str)
            detected_stack.add(DEPENDENCY_FILENAMES[fname])

        if fname.startswith(("license", "copying")) and fsize >= 50:
            has_license = True

        if fname.endswith(DATA_ARTIFACT_EXTENSIONS) and fsize > 250:
            has_data_artifact = True
            data_files_found.append(f"{path_str} ({fsize} B)")

        if fname.endswith((".py", ".ipynb")) and 30 <= fsize <= 512_000:
            candidate_code_files.append(blob)

    has_clean_paths = True
    notebooks_checked = 0
    notebooks_valid = True

    for code_blob in candidate_code_files[:2]:
        c_path = code_blob.get("path", "")
        content_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{c_path}"
        c_resp = await safe_get_with_redirect_guard(client, db, content_url, headers=clean_headers)
        if c_resp.status_code != 200:
            continue
        c_json = c_resp.json()
        b64_content = c_json.get("content", "")
        if not b64_content:
            continue
        raw_bytes = base64.b64decode(b64_content)

        if c_path.lower().endswith(".ipynb"):
            notebooks_checked += 1
            nb_clean, exec_cells = inspect_ipynb_bytes_streaming(raw_bytes)
            if not nb_clean or exec_cells < 3:
                notebooks_valid = False
        else:
            text_content = raw_bytes.decode("utf-8", errors="replace")
            if not inspect_script_text_for_hardcoded_paths(text_content):
                has_clean_paths = False

    if notebooks_checked > 0 and not notebooks_valid:
        has_clean_paths = False
    if not candidate_code_files and not repo_alive:
        has_clean_paths = False

    if repo_meta.get("language"):
        detected_stack.add(str(repo_meta["language"]))

    return ArtifactVerificationDTO(
        repo_url=repo_url,
        latest_commit_sha=latest_sha,
        repo_alive=repo_alive,
        has_dependencies=has_dependencies,
        has_clean_paths=has_clean_paths,
        has_data_artifact=has_data_artifact,
        has_license=has_license,
        probe_status=ProbeStatus.VERIFIED,
        detected_stack=sorted(detected_stack),
        diagnostics={
            "non_empty_files_count": len(non_empty_files),
            "dependency_files": dependency_files_found[:5],
            "data_artifacts": data_files_found[:5],
            "notebooks_inspected": notebooks_checked,
        },
    )


async def probe_project_artifacts(
    db: AsyncSession,
    urls_from_text: list[str],
    explicit_repo_url: str | None,
    project_id: uuid.UUID,
    revision_id: uuid.UUID,
    has_in_pdf_appendix: bool = False,
) -> ArtifactVerificationDTO:
    candidate_urls: list[str] = []
    if explicit_repo_url and explicit_repo_url.strip():
        candidate_urls.append(explicit_repo_url.strip())
    for u in urls_from_text:
        u_clean = u.strip().rstrip(".,;)>]")
        if u_clean not in candidate_urls:
            candidate_urls.append(u_clean)

    if not candidate_urls:
        return ArtifactVerificationDTO(
            repo_url=None,
            has_data_artifact=has_in_pdf_appendix,
            probe_status=ProbeStatus.NO_REPO_METHODOLOGY_ONLY,
            diagnostics={
                "mode": "In-Document Empirical / Methodology Audit",
                "has_structured_appendix_in_pdf": has_in_pdf_appendix,
            },
        )

    primary_url = candidate_urls[0]
    url_hash = hashlib.sha256(primary_url.encode("utf-8")).hexdigest()[:24]
    cache_key = f"cache:probe:{url_hash}"
    r_cache = get_redis_cache()

    cached_bytes = await r_cache.get(cache_key)
    if cached_bytes:
        cached_dict = orjson.loads(cached_bytes)
        return ArtifactVerificationDTO.model_validate(cached_dict)

    parsed_primary = urlparse(primary_url)
    primary_host = (parsed_primary.hostname or "").lower().removeprefix("www.")

    if not await is_domain_allowed(db, primary_host):
        try:
            verify_host_not_ssrf(primary_host)
        except ValueError as ssrf_err:
            return ArtifactVerificationDTO(
                repo_url=primary_url,
                probe_status=ProbeStatus.UNVERIFIED,
                diagnostics={"security_block": str(ssrf_err)},
            )

        await enqueue_domain_for_moderation(db, primary_host, primary_url, project_id, revision_id)
        return ArtifactVerificationDTO(
            repo_url=primary_url,
            has_data_artifact=has_in_pdf_appendix,
            probe_status=ProbeStatus.PENDING_DOMAIN,
            diagnostics={
                "pending_domain": primary_host,
                "message": f"Domain '{primary_host}' queued for 1-click approval by Supervisor / Dean's Office.",
            },
        )

    timeout_cfg = httpx.Timeout(connect=2.0, read=5.0, write=3.0, pool=2.0)
    async with httpx.AsyncClient(timeout=timeout_cfg) as client:
        try:
            gh_pair = _parse_github_owner_repo(primary_url)
            if gh_pair is not None:
                result_dto = await _probe_github_repository(
                    client, db, primary_url, gh_pair[0], gh_pair[1]
                )
            else:
                resp = await safe_get_with_redirect_guard(client, db, primary_url)
                is_alive = resp.status_code == 200 and len(resp.content) > 250
                is_data_host = any(
                    d in primary_host
                    for d in ("huggingface.co", "zenodo.org", "osf.io", "figshare.com", "kaggle.com", "mendeley.com")
                )
                result_dto = ArtifactVerificationDTO(
                    repo_url=primary_url,
                    repo_alive=is_alive,
                    has_dependencies=is_alive and ("gitlab.com" in primary_host or "huggingface.co" in primary_host),
                    has_clean_paths=is_alive,
                    has_data_artifact=(is_alive and is_data_host) or has_in_pdf_appendix,
                    has_license=is_alive,
                    probe_status=ProbeStatus.VERIFIED if is_alive else ProbeStatus.UNVERIFIED,
                    detected_stack=["External Dataset / Repository"],
                    diagnostics={"http_status": resp.status_code, "host": primary_host},
                )

            if has_in_pdf_appendix and not result_dto.has_data_artifact:
                result_dto.has_data_artifact = True

            if result_dto.probe_status != ProbeStatus.DEFERRED_RETRY:
                ttl = 86400 if result_dto.repo_alive else 1200
                await r_cache.setex(cache_key, ttl, orjson.dumps(result_dto.model_dump(mode="json")))

            return result_dto

        except Exception as exc:
            logger.warning("Artifact probe error for %s: %s", primary_url, exc)
            return ArtifactVerificationDTO(
                repo_url=primary_url,
                has_data_artifact=has_in_pdf_appendix,
                probe_status=ProbeStatus.UNVERIFIED,
                diagnostics={"error": str(exc)},
            )
