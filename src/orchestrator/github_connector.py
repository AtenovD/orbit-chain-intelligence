from __future__ import annotations

import base64
from typing import Any

import httpx


GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


def github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "Orbit-Agent-Orchestrator",
    }


async def fetch_github_context(token: str) -> dict[str, Any]:
    headers = github_headers(token)
    async with httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=30) as client:
        profile_response = await client.get("/user")
        profile_response.raise_for_status()
        repos_response = await client.get(
            "/user/repos",
            params={"per_page": 100, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"},
        )
        repos_response.raise_for_status()

    profile = profile_response.json()
    repositories = [
        {
            "name": repo["full_name"],
            "description": repo.get("description"),
            "language": repo.get("language"),
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "private": repo.get("private", False),
            "updated_at": repo.get("updated_at"),
            "url": repo.get("html_url"),
            "topics": repo.get("topics", []),
        }
        for repo in repos_response.json()
    ]
    return {
        "profile": {
            "login": profile["login"],
            "name": profile.get("name"),
            "bio": profile.get("bio"),
            "company": profile.get("company"),
            "public_repos": profile.get("public_repos", 0),
            "followers": profile.get("followers", 0),
            "url": profile.get("html_url"),
        },
        "repositories": repositories,
        "repository_count": len(repositories),
    }


async def fetch_repository_tree(token: str, full_name: str, ref: str | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=GITHUB_API, headers=github_headers(token), timeout=30) as client:
        repo_response = await client.get(f"/repos/{full_name}")
        repo_response.raise_for_status()
        repo = repo_response.json()
        branch = ref or repo.get("default_branch") or "main"
        tree_response = await client.get(f"/repos/{full_name}/git/trees/{branch}", params={"recursive": "1"})
        tree_response.raise_for_status()
    tree = [
        {"path": item.get("path"), "type": item.get("type"), "size": item.get("size"), "sha": item.get("sha")}
        for item in tree_response.json().get("tree", [])[:5000]
        if item.get("path")
    ]
    return {"repository": full_name, "ref": branch, "truncated": tree_response.json().get("truncated", False), "tree": tree}


async def fetch_repository_file(token: str, full_name: str, path: str, ref: str | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=GITHUB_API, headers=github_headers(token), timeout=30) as client:
        response = await client.get(f"/repos/{full_name}/contents/{path}", params={"ref": ref} if ref else None)
        response.raise_for_status()
    value = response.json()
    if isinstance(value, list):
        return {"repository": full_name, "path": path, "entries": value}
    content = ""
    if value.get("encoding") == "base64" and value.get("content"):
        content = base64.b64decode(value["content"]).decode("utf-8", errors="replace")
    return {
        "repository": full_name,
        "path": path,
        "sha": value.get("sha"),
        "size": value.get("size"),
        "content": content[:1_000_000],
        "truncated": len(content) > 1_000_000,
        "url": value.get("html_url"),
    }


async def search_repository_code(token: str, full_name: str, query: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=GITHUB_API, headers=github_headers(token), timeout=30) as client:
        response = await client.get("/search/code", params={"q": f"{query} repo:{full_name}", "per_page": 50})
        response.raise_for_status()
    return [
        {
            "name": item.get("name"),
            "path": item.get("path"),
            "sha": item.get("sha"),
            "url": item.get("html_url"),
            "score": item.get("score"),
        }
        for item in response.json().get("items", [])
    ]


def github_memory_markdown(data: dict[str, Any]) -> str:
    profile = data["profile"]
    repos = data["repositories"][:40]
    lines = [
        "## Connected source: GitHub",
        f"- Account: {profile.get('name') or profile['login']} (@{profile['login']})",
        f"- Bio: {profile.get('bio') or 'not specified'}",
        f"- Followers: {profile.get('followers', 0)}",
        f"- Accessible repositories: {data['repository_count']}",
        "",
        "### Repository signals",
    ]
    for repo in repos:
        signals = ", ".join(
            part
            for part in [
                repo.get("language"),
                f"{repo.get('stars', 0)} stars",
                f"{repo.get('forks', 0)} forks",
                "private" if repo.get("private") else "public",
            ]
            if part
        )
        lines.append(f"- **{repo['name']}** — {repo.get('description') or 'no description'} ({signals})")
    return "\n".join(lines)
