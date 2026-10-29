"""Fixed, fictional examples. No settings, database, network or user state."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoAnnouncement:
    id: str
    title: str
    excerpt: str
    category: str
    published: str | None


DEMO_ANNOUNCEMENTS = (
    DemoAnnouncement('demo-scholarship', '【合成示範】學習支持獎學金申請',
        '虛構情境：開放學生申請學習支持獎學金，須準備申請表與在學證明。'
        '示範報名截止為 2026 年 9 月 20 日。這不是實際申請資訊。', '獎學金', '2026-09-01'),
    DemoAnnouncement('demo-event', '【合成示範】校園職涯探索活動',
        '虛構情境：職涯探索活動於 2026 年 9 月 25 日舉辦，示範報名截止為 9 月 18 日。'
        '報名截止與活動日期是不同資訊；這不是實際活動。', '活動', '2026-09-02'),
    DemoAnnouncement('demo-notice', '【合成示範】行政服務資訊更新', '', '行政通知', None),
)


def list_demo_announcements(q: str = '', category: str = '') -> tuple[DemoAnnouncement, ...]:
    keyword = q.strip().casefold()
    return tuple(item for item in DEMO_ANNOUNCEMENTS
                 if (not category or item.category == category)
                 and (not keyword or keyword in (item.title + '\n' + item.excerpt).casefold()))


def get_demo_announcement(demo_id: str) -> DemoAnnouncement | None:
    return next((item for item in DEMO_ANNOUNCEMENTS if item.id == demo_id), None)
