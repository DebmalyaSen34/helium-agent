from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class GraderConfig:
    type: str
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraderConfig":
        return cls(
            type=data["type"],
            params=data.get("params", {})
        )

@dataclass
class TaskConfig:
    id: str
    description: str
    category: str
    input_prompt: str
    setup: Optional[str] = None
    teardown: Optional[str] = None
    graders: List[GraderConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskConfig":
        return cls(
            id=data["id"],
            description=data["description"],
            category=data["category"],
            input_prompt=data["input_prompt"],
            setup=data.get("setup"),
            teardown=data.get("teardown"),
            graders=[GraderConfig.from_dict(g) for g in data.get("graders", [])]
        )
