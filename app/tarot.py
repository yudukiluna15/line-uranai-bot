"""
タロットカード(大アルカナ22枚)の抽選。
総合運の「今日の1枚」演出に使う。
"""
import random

from app.config import settings

MAJOR_ARCANA = [
    "愚者", "魔術師", "女教皇", "女帝", "皇帝", "教皇", "恋人", "戦車",
    "力", "隠者", "運命の輪", "正義", "吊るされた男", "死神", "節制",
    "悪魔", "塔", "星", "月", "太陽", "審判", "世界",
]

# 名前の響きだけで不安にさせやすいカード。AIへの鑑定文生成時に、
# 前向きな伝え方の指針として一緒に渡す(ai_service.generate_fortuneが利用)。
CAUTION_CARD_NOTES = {
    "死神": "終わりそのものではなく、次の段階への切り替わりのサインとして前向きに扱う",
    "塔": "崩れることで無理をしていた部分が見え、本来の姿に戻るきっかけとして扱う",
    "悪魔": "縛られている思い込みに気づくきっかけ、という気づきの意味で扱う",
    "吊るされた男": "あえて立ち止まることで、新しい視点が得られるという意味で扱う",
    "月": "はっきりしない不安の先に、必ず朝が来るという希望も添えて扱う",
}


def draw_card() -> dict:
    """
    カード名と正位置/逆位置をランダムに返す。
    不安を煽りやすいカードの場合、前向きな伝え方のヒント(note)も付ける。
    """
    card = random.choice(MAJOR_ARCANA)
    is_upright = random.random() > 0.5
    return {
        "name": card,
        "orientation": "正位置" if is_upright else "逆位置",
        "note": CAUTION_CARD_NOTES.get(card, ""),
    }


def get_card_image_url(card_name: str) -> str | None:
    """
    カード画像を用意し、TAROT_IMAGE_BASE_URLを設定した場合にURLを返す。
    未設定の場合はNone(画像なしで運用する)。
    画像ファイル名は、MAJOR_ARCANAの並び順に対応する2桁の連番
    (例: 愚者→00.jpg、世界→21.jpg)を想定している。
    """
    if not settings.TAROT_IMAGE_BASE_URL:
        return None
    if card_name not in MAJOR_ARCANA:
        return None

    index = MAJOR_ARCANA.index(card_name)
    base = settings.TAROT_IMAGE_BASE_URL.rstrip("/")
    return f"{base}/{index:02d}.jpg"
