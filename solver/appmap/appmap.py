import json
from typing import List, Union, cast


class AppMap:
    def __init__(self, data: Union[str, dict]):
        if isinstance(data, str):
            data = json.loads(data)

        self.data: dict = cast(dict, data)

    def list_locations(self):
        # Recursively list all classMap entries
        def collect_locations(cls: dict, locations: List[str]) -> List[str]:
            if cls.get("location"):
                locations.append(cls["location"])

            for child in cls.get("children", []):
                collect_locations(child, locations)

            return locations

        locations: List[str] = []
        for cls in self.data["classMap"]:
            collect_locations(cls, locations)
        return locations
