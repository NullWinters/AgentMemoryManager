import requests

from .exceptions import MemoryServiceError
from .session import Session


class MemoryClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session_headers = {"X-API-Key": api_key} if api_key else {}

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method, url, headers=self.session_headers, json=json, params=params
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = {}
            raise MemoryServiceError(
                f"API error: {resp.text}",
                status_code=resp.status_code,
                response=detail,
            )
        if resp.status_code == 204:
            return {}
        return resp.json() if resp.text else {}

    def setup(
        self,
        agent_id: str,
        name: str | None = None,
        persona: str = "",
        config: dict | None = None,
    ) -> dict:
        payload = {
            "agent_id": agent_id,
            "name": name or agent_id,
            "persona": persona,
            "config": config or {},
        }
        try:
            return self._request("POST", "/api/v1/agents", json=payload)
        except MemoryServiceError as e:
            if e.status_code != 409:
                raise
            return self._request("PATCH", f"/api/v1/agents/{agent_id}", json={
                "name": payload["name"],
                "persona": persona,
                "config": config or {},
            })

    def ensure_user(self, user_id: str) -> dict:
        return self._request("PUT", f"/api/v1/users/{user_id}")

    def add_skill_to_agent(self, agent_id: str, skill_id: str) -> dict:
        return self._request("POST", f"/api/v1/agents/{agent_id}/skills/{skill_id}")

    def create_skill(
        self, name: str, trigger_keys: list[str], prompt_snippet: str = ""
    ) -> dict:
        return self._request(
            "POST",
            "/api/v1/skills",
            json={
                "name": name,
                "trigger_keys": trigger_keys,
                "prompt_snippet": prompt_snippet,
            },
        )

    def session_start(
        self, agent_id: str, user_id: str, session_id: str | None = None
    ) -> Session:
        self.ensure_user(user_id)
        data = self._request(
            "POST",
            "/api/v1/sessions",
            json={
                "agent_id": agent_id,
                "user_id": user_id,
                "session_id": session_id,
            },
        )
        return Session(
            client=self,
            agent_id=agent_id,
            user_id=user_id,
            session_id=data["session_id"],
        )

    def get_user_profile(self, user_id: str) -> dict:
        return self._request("GET", f"/api/v1/users/{user_id}/profile")

    def update_user_profile(self, user_id: str, profile: dict) -> dict:
        return self._request(
            "PATCH",
            f"/api/v1/users/{user_id}/profile",
            json={"profile": profile},
        )

    def add_user_memory(
        self, user_id: str, type: str, content: str, importance: float = 0.5
    ) -> dict:
        return self._request(
            "POST",
            f"/api/v1/users/{user_id}/memories",
            json={"type": type, "content": content, "importance": importance},
        )

    def search_user_memories(
        self,
        user_id: str,
        query: str = "",
        top_k: int = 10,
        type: str | None = None,
    ) -> list:
        params: dict = {"top_k": top_k}
        if query:
            params["query"] = query
        if type:
            params["type"] = type
        return self._request("GET", f"/api/v1/users/{user_id}/memories", params=params)

    def stats(self) -> dict:
        return self._request("GET", "/api/v1/stats")

    def health(self) -> dict:
        return self._request("GET", "/api/v1/health")
