from . import hanatour, interpark_tour, monkeytravel, myrealtrip, thaiclub, waug, wittour

PLATFORM_CRAWLERS = {
    "마이리얼트립": myrealtrip.crawl,
    "하나투어": hanatour.crawl,
    "와그": waug.crawl,
    "인터파크 투어": interpark_tour.crawl,
    "더블유아이티": wittour.crawl,
    "타이클럽": thaiclub.crawl,
    "몽키트래블": monkeytravel.crawl,
}
