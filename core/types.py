from dataclasses import dataclass

@dataclass
class Item:
    platform: str
    title: str
    price: str
    link: str