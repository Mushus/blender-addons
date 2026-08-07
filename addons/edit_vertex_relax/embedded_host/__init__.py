# ツール側は registry の公開 API だけを使う。host 実装の差し替え点。
from .registry import ToolSpec, register_tool, unregister_tool

__all__ = ["ToolSpec", "register_tool", "unregister_tool"]
