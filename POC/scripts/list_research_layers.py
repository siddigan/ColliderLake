from __future__ import annotations

from _bootstrap import add_workspace_to_path

add_workspace_to_path()

from src.research.registry import DIAMOND_LAYERS


def main() -> None:
    for layer in DIAMOND_LAYERS:
        print(f"{layer.order}. {layer.name}")
        print(f"   {layer.purpose}")
        print(f"   tables: {', '.join(layer.planned_tables)}")


if __name__ == "__main__":
    main()

