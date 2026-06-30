from .context import Context


class Session:
    def __init__(self, client, agent_id: str, user_id: str, session_id: str):
        self._client = client
        self.agent_id = agent_id
        self.user_id = user_id
        self.session_id = session_id

    def add_message(
        self,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> dict:
        return self._client._request(
            "POST",
            f"/api/v1/sessions/{self.session_id}/messages",
            json={
                "role": role,
                "content": content,
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
            },
        )

    def inject_context(self, query: str | None = None, **opts) -> Context:
        body = {
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "query": query,
            "options": {**opts},
        }
        data = self._client._request("POST", "/api/v1/context", json=body)
        return Context.from_response(data)

    def end(self) -> dict:
        return self._client._request(
            "PATCH",
            f"/api/v1/sessions/{self.session_id}",
            json={"status": "completed"},
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.end()
