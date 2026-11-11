"""Contexte d'une requête authentifiée : qui, dans quelle société, avec quels droits."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequestContext:
    user_id: int
    is_superuser: bool
    company_id: int | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission: str) -> bool:
        """Vérifie une permission « module:action ».

        Jokers acceptés dans les rôles : « * » (tout) et « module:* » (tout le module).
        """
        if self.is_superuser:
            return True
        module = permission.split(":", 1)[0]
        return bool({permission, f"{module}:*", "*"} & self.permissions)
