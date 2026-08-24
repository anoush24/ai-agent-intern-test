from dataclasses import dataclass, field


@dataclass
class Session:
    history: list[dict[str, str]] = field(default_factory=list)
    turn_index: int = 0


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def _get_or_create(self, session_id: str) -> Session:
        return self._sessions.setdefault(session_id, Session())

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        return self._get_or_create(session_id).history

    def next_turn_index(self, session_id: str) -> int:
        session = self._get_or_create(session_id)
        session.turn_index += 1
        return session.turn_index

    def append(self, session_id: str, role: str, content: str):
        self._get_or_create(session_id).history.append({"role": role, "content": content})

    def reset(self, session_id: str):
        self._sessions[session_id] = Session()