"""Git MCP 服务：GitLab API 封装（issues、commits、项目等）"""
import os
import urllib.parse
import yaml
import httpx
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_project_root = Path(__file__).resolve().parent.parent
_config: Optional[Dict[str, Any]] = None
_clients: Dict[str, Any] = {}


def _expand_env_vars(obj: Any) -> Any:
    """递归展开配置中的 ${VAR} 或 ${VAR:-default}"""
    if isinstance(obj, str):
        import re
        if "${" not in obj:
            return obj
        # ${VAR:-default}
        m = re.match(r"^\$\{([^:}]+)(?::-([^}]*))?\}$", obj.strip())
        if m:
            key, default = m.group(1), (m.group(2) or "")
            return os.environ.get(key, default)
        # ${VAR}
        return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def _load_config() -> Dict[str, Any]:
    global _config
    if _config is not None:
        return _config
    config_path = _project_root / "git.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        _config = _expand_env_vars(raw)
        return _config
    except Exception as e:
        logger.error(f"加载 git 配置失败: {e}")
        _config = {}
        return _config


def _get_simple_repo_name(repo_name: str) -> str:
    if "/" in repo_name:
        return repo_name.split("/")[-1]
    return repo_name


def _get_client(repo_name: str):
    global _clients
    cfg = _load_config()
    simple = _get_simple_repo_name(repo_name)
    if simple in _clients:
        return _clients[simple]
    repos = cfg.get("repositories", {})
    repo_config = repos.get(simple)
    if not repo_config:
        logger.error(f"仓库配置不存在: {simple}")
        return None
    gitlab = cfg.get("gitlab", {})
    server = gitlab.get("server", "gitlab.example.com")
    port = gitlab.get("port", 80)
    base_url = f"http://{server}:{port}/api/v4"
    token = repo_config.get("token", "")
    headers = {"PRIVATE-TOKEN": token} if token else {}
    _clients[simple] = {"base_url": base_url, "headers": headers, "project_id": repo_config.get("project_id", "")}
    return _clients[simple]


def _encode_path(project_path) -> str:
    if isinstance(project_path, (int, float)):
        return str(project_path)
    if isinstance(project_path, str):
        return urllib.parse.quote(project_path, safe="")
    return str(project_path)


async def list_issues(repo_name: str, per_page: int = 20, state: str = "all",
                      created_after: str = None, created_before: str = None,
                      updated_after: str = None) -> List[Dict[str, Any]]:
    client = _get_client(repo_name)
    if not client:
        return [{"error": "GitLab 客户端未初始化或仓库未配置"}]
    project_id = client.get("project_id", "")
    if not project_id:
        return [{"error": "仓库 project_id 未配置"}]
    url = f"{client['base_url']}/projects/{_encode_path(project_id)}/issues"
    params = {"per_page": per_page, "state": state}
    if created_after:
        params["created_after"] = created_after
    if created_before:
        params["created_before"] = created_before
    if updated_after:
        params["updated_after"] = updated_after
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            r = await c.get(url, headers=client["headers"], params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"获取 issues 失败: {e}")
            return [{"error": str(e)}]


async def get_issue(repo_name: str, issue_id: int) -> Dict[str, Any]:
    client = _get_client(repo_name)
    if not client:
        return {"error": "GitLab 客户端未初始化或仓库未配置"}
    project_id = client.get("project_id", "")
    if not project_id:
        return {"error": "仓库 project_id 未配置"}
    url = f"{client['base_url']}/projects/{_encode_path(project_id)}/issues/{issue_id}"
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            r = await c.get(url, headers=client["headers"])
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"获取 issue 详情失败: {e}")
            return {"error": str(e)}


async def list_issue_notes(repo_name: str, issue_id: int, per_page: int = 20) -> List[Dict[str, Any]]:
    client = _get_client(repo_name)
    if not client:
        return [{"error": "GitLab 客户端未初始化或仓库未配置"}]
    project_id = client.get("project_id", "")
    if not project_id:
        return [{"error": "仓库 project_id 未配置"}]
    url = f"{client['base_url']}/projects/{_encode_path(project_id)}/issues/{issue_id}/notes"
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            r = await c.get(url, headers=client["headers"], params={"per_page": per_page})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"获取 issue 评论失败: {e}")
            return [{"error": str(e)}]


async def list_commits(repo_name: str, ref_name: str = "main", per_page: int = 20,
                      since: str = None, until: str = None) -> List[Dict[str, Any]]:
    client = _get_client(repo_name)
    if not client:
        return [{"error": "GitLab 客户端未初始化或仓库未配置"}]
    project_id = client.get("project_id", "")
    if not project_id:
        return [{"error": "仓库 project_id 未配置"}]
    url = f"{client['base_url']}/projects/{_encode_path(project_id)}/repository/commits"
    params = {"ref_name": ref_name, "per_page": per_page}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            r = await c.get(url, headers=client["headers"], params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"获取提交记录失败: {e}")
            return [{"error": str(e)}]


async def search_content(repo_name: str, query: str, per_page: int = 20) -> Dict[str, Any]:
    issues = await list_issues(repo_name, per_page=per_page)
    commits = await list_commits(repo_name, per_page=per_page)
    q = query.lower()
    matching_issues = [i for i in issues if "error" not in i and q in ((i.get("title", "") + " " + (i.get("description") or "")).lower())]
    matching_commits = [c for c in commits if "error" not in c and q in ((c.get("message", "") + " " + (c.get("title", "") or "")).lower())]
    return {"issues": matching_issues, "commits": matching_commits}


async def list_projects(per_page: int = 20) -> List[Dict[str, Any]]:
    cfg = _load_config()
    repos = cfg.get("repositories", {})
    if not repos:
        return [{"error": "未配置仓库"}]
    first_repo = list(repos.keys())[0]
    client = _get_client(first_repo)
    if not client:
        return [{"error": "GitLab 客户端未初始化"}]
    url = f"{client['base_url']}/projects"
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            r = await c.get(url, headers=client["headers"], params={"per_page": per_page})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"获取项目列表失败: {e}")
            return [{"error": str(e)}]


async def get_project(project_id: str) -> Dict[str, Any]:
    cfg = _load_config()
    repos = cfg.get("repositories", {})
    if not repos:
        return {"error": "未配置仓库"}
    first_repo = list(repos.keys())[0]
    client = _get_client(first_repo)
    if not client:
        return {"error": "GitLab 客户端未初始化"}
    url = f"{client['base_url']}/projects/{_encode_path(project_id)}"
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            r = await c.get(url, headers=client["headers"])
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"获取项目详情失败: {e}")
            return {"error": str(e)}


async def list_branches(project_id: str) -> List[Dict[str, Any]]:
    cfg = _load_config()
    repos = cfg.get("repositories", {})
    if not repos:
        return [{"error": "未配置仓库"}]
    first_repo = list(repos.keys())[0]
    client = _get_client(first_repo)
    if not client:
        return [{"error": "GitLab 客户端未初始化"}]
    url = f"{client['base_url']}/projects/{_encode_path(project_id)}/repository/branches"
    async with httpx.AsyncClient(timeout=30.0) as c:
        try:
            r = await c.get(url, headers=client["headers"])
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"获取分支列表失败: {e}")
            return [{"error": str(e)}]


async def search_repositories(query: str) -> Dict[str, Any]:
    cfg = _load_config()
    repos = cfg.get("repositories", {})
    matching = []
    q = query.lower()
    for name, repo in repos.items():
        desc = (repo.get("description") or "").lower()
        if q in desc or q in name.lower():
            matching.append({"name": name, "description": repo.get("description", ""), "project_id": repo.get("project_id", "")})
    return {"repositories": matching, "count": len(matching)}


def register_tools() -> Dict[str, Any]:
    return {
        "list_issues": list_issues,
        "get_issue": get_issue,
        "list_issue_notes": list_issue_notes,
        "search_content": search_content,
        "list_projects": list_projects,
        "get_project": get_project,
        "list_branches": list_branches,
        "list_commits": list_commits,
        "search_repositories": search_repositories,
    }


def get_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "git_list_issues", "description": "获取指定 GitLab 仓库的 issues 列表，支持按日期过滤", "parameters": {"type": "object", "properties": {"repo_name": {"type": "string"}, "per_page": {"type": "integer"}, "state": {"type": "string"}, "created_after": {"type": "string"}, "created_before": {"type": "string"}, "updated_after": {"type": "string"}}, "required": ["repo_name"]}}},
        {"type": "function", "function": {"name": "git_get_issue", "description": "获取指定仓库的单个 issue 详情", "parameters": {"type": "object", "properties": {"repo_name": {"type": "string"}, "issue_id": {"type": "integer"}}, "required": ["repo_name", "issue_id"]}}},
        {"type": "function", "function": {"name": "git_list_issue_notes", "description": "获取指定仓库的 issue 评论列表", "parameters": {"type": "object", "properties": {"repo_name": {"type": "string"}, "issue_id": {"type": "integer"}, "per_page": {"type": "integer"}}, "required": ["repo_name", "issue_id"]}}},
        {"type": "function", "function": {"name": "git_search_content", "description": "搜索仓库中的 issues 与提交记录", "parameters": {"type": "object", "properties": {"repo_name": {"type": "string"}, "query": {"type": "string"}, "per_page": {"type": "integer"}}, "required": ["repo_name", "query"]}}},
        {"type": "function", "function": {"name": "git_list_projects", "description": "获取 GitLab 项目列表", "parameters": {"type": "object", "properties": {"per_page": {"type": "integer"}}}}},
        {"type": "function", "function": {"name": "git_search_repositories", "description": "根据描述搜索已配置的仓库", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "git_list_commits", "description": "获取指定仓库的提交记录，支持按日期过滤", "parameters": {"type": "object", "properties": {"repo_name": {"type": "string"}, "ref_name": {"type": "string"}, "per_page": {"type": "integer"}, "since": {"type": "string"}, "until": {"type": "string"}}, "required": ["repo_name"]}}},
        {"type": "function", "function": {"name": "git_get_project", "description": "获取项目详情", "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}}},
        {"type": "function", "function": {"name": "git_list_branches", "description": "获取指定项目的分支列表", "parameters": {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]}}},
    ]


TOOLS = register_tools()
TOOL_DEFINITIONS = get_tool_definitions()
