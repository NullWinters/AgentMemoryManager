from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    prompt_snippet: str


@dataclass
class AgentMemory:
    agent_id: str
    persona: str
    skills: list[Skill] = field(default_factory=list)


@dataclass
class Fragment:
    type: str
    content: str
    score: float = 0.0


@dataclass
class UserMemory:
    profile: dict = field(default_factory=dict)
    fragments: list[Fragment] = field(default_factory=list)


@dataclass
class Message:
    role: str
    content: str
    tool_name: str | None = None


@dataclass
class SessionMemory:
    session_id: str
    message_count: int = 0
    summary: str | None = None
    messages: list[Message] = field(default_factory=list)


@dataclass
class Context:
    agent_memory: AgentMemory
    user_memory: UserMemory
    session_memory: SessionMemory

    @classmethod
    def from_response(cls, data: dict) -> "Context":
        am = data["agent_memory"]
        um = data["user_memory"]
        sm = data["session_memory"]

        return cls(
            agent_memory=AgentMemory(
                agent_id=am["agent_id"],
                persona=am.get("persona") or "",
                skills=[
                    Skill(name=s["name"], prompt_snippet=s.get("prompt_snippet", ""))
                    for s in am.get("skills") or []
                ],
            ),
            user_memory=UserMemory(
                profile=um.get("profile") or {},
                fragments=[
                    Fragment(
                        type=f["type"],
                        content=f["content"],
                        score=f.get("score") or f.get("importance") or 0.0,
                    )
                    for f in um.get("fragments") or []
                ],
            ),
            session_memory=SessionMemory(
                session_id=sm["session_id"],
                message_count=sm.get("message_count") or 0,
                summary=sm.get("summary"),
                messages=[
                    Message(
                        role=m["role"],
                        content=m["content"],
                        tool_name=m.get("tool_name"),
                    )
                    for m in sm.get("messages") or []
                ],
            ),
        )

    def to_messages(self) -> list[dict]:
        """将三层记忆拼接为标准 OpenAI 消息列表"""
        messages = []

        system_parts = [self.agent_memory.persona]
        for skill in self.agent_memory.skills:
            system_parts.append(f"\n[技能：{skill.name}]\n{skill.prompt_snippet}")
        if self.user_memory.profile:
            profile_str = ", ".join(
                f"{k}={v.get('v', v)}" if isinstance(v, dict) else f"{k}={v}"
                for k, v in self.user_memory.profile.items()
            )
            system_parts.append(f"\n用户偏好：{profile_str}")
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

        for frag in self.user_memory.fragments:
            messages.append({"role": "user", "content": f"[历史记忆] {frag.content}"})

        if self.session_memory.summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"[会话摘要] {self.session_memory.summary}",
                }
            )

        for msg in self.session_memory.messages:
            messages.append({"role": msg.role, "content": msg.content})

        return messages
