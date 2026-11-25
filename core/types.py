from dataclasses import dataclass

@dataclass
class Item:
    platform: str
    title: str
    price: str
    link: str
    supplier_id: str = ""
    supplier_name: str = ""
    merchant_name: str = ""
