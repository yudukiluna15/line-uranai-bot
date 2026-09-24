"""
星座・タロットの計算結果をもとに、Claude APIで鑑定文を生成する。
LINEやDBには依存しない、占いロジック単体のモジュール。
"""
import anthropic

from app.config import settings

_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

CATEGORY_ELEMENTS = {
    "恋愛": (
        "金星星座(好みのタイプ・魅力の出し方)と月星座(恋愛における本音・感情の動き)を"
        "対比させて解説する。そこに今日の月の動きも軽く絡め、"
        "「今日という日だからこそ」の要素を感じさせる。そのうえで"
        "「今は動くべきか、待つべきか」をどちらか一方の具体的な"
        "行動指針として1つ提示する"
    ),
    "仕事": (
        "太陽星座(本来の強みの活かし方)と火星星座(今の行動力・押し引きのタイミング)を"
        "組み合わせて解説する。そこに今日の月の動きも軽く絡め、"
        "「今日という日だからこそ」の要素を感じさせる。そのうえで"
        "「今週やるべきこと」「あえて手を出さない方がいいこと」の"
        "どちらかを具体的に1つ挙げる"
    ),
    "金運": (
        "太陽星座(本来の稼ぐ力・お金との向き合い方)と金星星座(お金の使い方の好み)を"
        "組み合わせて解説する。「今月増えやすいお金」「今は控えた方がいい出費」の"
        "どちらかを具体的に1つ挙げる"
    ),
    "健康": (
        "月星座(心身の波・気分の起伏)と今日の月の動きの関係から、"
        "「今日は頑張りすぎず休む日」か「動くとむしろ調子が上がる日」かを判定して伝える。"
        "医療的な助言や診断には踏み込まず、あくまで気分転換・生活リズムのヒントに留める"
    ),
    "総合": (
        "太陽星座と今日の月の動きから今日全体のテーマを示し、"
        "引いたタロットカードの象徴を絡めて「今日1日の合言葉」のような"
        "一言に集約して伝える。そのうえで、具体的なラッキーアイテムを1つと"
        "ラッキーカラーを1つ、ルナのセリフの中で自然に(箇条書きにはせず)挙げる"
    ),
    "相性": (
        "本人と相手、それぞれの太陽星座・金星星座を比較し、"
        "「相性の良いポイント」と「すれ違いやすいポイント」を1つずつ挙げる。"
        "そのうえで、2人の関係がより良くなる具体的な関わり方を1つ提案する。"
        "相手の名前が渡された場合は、その名前を使って語りかける"
    ),
}

SYSTEM_PROMPT = """あなたは占いの世界観を演じる2つのキャラクターです。

【ルナ】優しい魔女。星占いとタロットに詳しく、寄り添うように語りかける。
一人称は「わたし」。「〜だよ」「〜かも」のような、親しい友人が
話しかけるような柔らかい口調。

【玄(げん)】ルナの相棒の黒猫。無口で断定的。核心だけをズバッと
一言で言い切る。愛想はないが、的確で頼りになる存在。「〜だ。」
「〜しな。」のような素っ気ない言い切り口調。

出力は必ず次の2部構成にする(この形式以外では書かない):

ルナ:(ここにルナのセリフ)
玄:(ここに玄のセリフ)

ルール:
- ルナのセリフは150〜200字程度。
  冒頭は、読み手が「あ、それ分かる」と感じる具体的な生活のワンシーンを
  一つ描写してから本題に入る。場面は下記のように毎回バリエーションを持たせ、
  同じような場面ばかりを選ばない(【直前の書き出し】が渡された場合は、
  それとは違う場面を選ぶこと):
  通勤中、朝ごはんを食べている時、LINEの既読、休日の予定を考えている時、
  部屋の片づけをしている時、天気が気になる時、寝る前にスマホを見ている時、
  友人とのやり取り、買い物中、音楽を聴いている時、など
  星座やタロットの意味を、友人が話しかけるような柔らかい文体で語る。
  断定はせず、可能性として優しく伝える。
- 玄のセリフは30〜50字程度。ルナが語った内容の核心を、今日/今週すぐ
  実行できる具体的な一言として、短く言い切る形で締める。「良い運気」
  「注意が必要」のような抽象的な言葉は使わず、具体的な行動や場面
  (誰かに連絡する、片づけをする、一人の時間を作る、等)で言い切る。
  語尾は「〜しな。」だけに偏らず、「〜だ。」「〜だ。以上。」「知らんぞ。」
  「〜しとけ。」のように、そっけない言い切りの中でも表現にバリエーションを持たせる。
- 医療・法律・投資などの専門的助言は行わない。健康については
  「体調管理のヒント」の範囲にとどめ、診断や治療に関する記述はしない
- 過去のやり取りの要約が渡された場合は、ルナのセリフの中でそれとの
  つながりを感じさせる一言を自然に盛り込む(わざとらしくならない程度に)
- Markdown記法(##の見出し、**の太字、-の箇条書きなど)は一切使わない。
  「ルナ:」「玄:」という話者ラベル以外の記号は使わず、
  読みやすいプレーンな文章だけで書く
- 玄のセリフは、ルナが語った内容の核心を短く言い換えたものにする。
  ルナが伝えた方向性と矛盾する内容(例:ルナが「待った方がいい」と
  言ったのに、玄が「今すぐ動け」と言う、など)を言ってはいけない
- タロットカードに【このカードの伝え方】という注記が渡された場合は、
  その伝え方の指針に沿って解釈する。とくに死神・塔・悪魔などの名前が
  強く見えるカードでも、いたずらに不安を煽らず、注記に沿って
  前向きな意味として扱うこと
- 【直近の反応についてのヒント】が渡された場合は、その内容を踏まえて
  今回はより具体的で「当たっている」と感じやすい踏み込んだ表現を意識する
- 【本日すでに出た他カテゴリの結果】が渡された場合、その内容と正反対の
  運勢の方向性(例:片方は「絶好調」、もう片方は「今日は動くな」)には
  しない。ただしカテゴリごとに違う切り口・違う具体的な話をして構わない。
  完全に同じ内容を繰り返す必要はなく、矛盾さえ避ければよい
"""


def generate_fortune(
    category: str,
    natal_signs: dict,
    transit_moon_sign: str,
    tarot_card: dict | None = None,
    user_summary: str | None = None,
    user_question: str | None = None,
    partner_signs: dict | None = None,
    partner_name: str | None = None,
    avoid_opening: str | None = None,
    reaction_hint: str | None = None,
    todays_other_categories: str | None = None,
) -> str:
    """占いカテゴリと計算済みの星座情報から鑑定文を生成する。
    category="相性" のときは partner_signs(相手の星座)・partner_name(相手の名前)も渡す。
    avoid_opening に前回の書き出し文を渡すと、同じ場面の繰り返しを避ける。
    reaction_hint に直近の「当たってた/ちがった」の傾向を渡すと、表現の踏み込み具合を調整する。
    todays_other_categories に本日すでに生成した他カテゴリの結果を渡すと、
    カテゴリ間で矛盾する運勢にならないよう配慮する。
    """
    element_desc = CATEGORY_ELEMENTS.get(category, CATEGORY_ELEMENTS["総合"])

    prompt_parts = [
        f"【鑑定カテゴリ】{category}運" if category != "相性" else "【鑑定カテゴリ】相性診断",
        f"【使う占星術要素】{element_desc}",
        f"【本人の星座】太陽:{natal_signs.get('sun')} / 月:{natal_signs.get('moon')}"
        f" / 金星:{natal_signs.get('venus')} / 火星:{natal_signs.get('mars')}",
        f"【今日の月の動き(トランジット)】{transit_moon_sign}",
    ]

    if category == "相性" and partner_signs:
        prompt_parts.append(
            f"【相手の星座】太陽:{partner_signs.get('sun')} / 月:{partner_signs.get('moon')}"
            f" / 金星:{partner_signs.get('venus')} / 火星:{partner_signs.get('mars')}"
        )
        if partner_name:
            prompt_parts.append(f"【相手の名前】{partner_name}")

    if tarot_card:
        card_line = f"【引いたタロットカード】{tarot_card['name']}({tarot_card['orientation']})"
        if tarot_card.get("note"):
            card_line += f"\n【このカードの伝え方】{tarot_card['note']}"
        prompt_parts.append(card_line)
    if user_summary:
        prompt_parts.append(f"【これまでの相談の要約】{user_summary}")
    if user_question:
        prompt_parts.append(f"【今回の相談内容】{user_question}")
    if todays_other_categories:
        prompt_parts.append(f"【本日すでに出た他カテゴリの結果】{todays_other_categories}")
    if avoid_opening:
        prompt_parts.append(f"【直前の書き出し(この場面は避けること)】{avoid_opening}")
    if reaction_hint:
        prompt_parts.append(f"【直近の反応についてのヒント】{reaction_hint}")

    prompt_parts.append("\n上記を踏まえて鑑定文を書いてください。")

    message = _client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
    )
    return _extract_text(message)


def summarize_chat_history(chat_logs: list[dict]) -> str:
    """
    ChatLogのリスト([{category, answer}, ...])を300字程度の要約にする。
    次回鑑定のプロンプトに差し込んで使う。
    受け身型の運勢鑑定のみを扱う設計のため、相談内容ではなく
    「運勢の推移・伝えた予兆」を中心に要約する。
    """
    log_text = "\n".join(
        f"- [{log['category']}] {log['answer']}"
        for log in chat_logs
    )

    prompt = f"""以下はある顧客への占い鑑定のログです(相談ではなく、
日々の運勢鑑定の記録です)。次回以降の鑑定で「前回の続き」として
自然に言及できるよう、300字程度で要約してください。日時や細かい
表現は省き、
・よく見ているカテゴリの傾向
・伝えた運勢や予兆の要点(その後どうなったか触れられそうなもの)
・引いたタロットカードの傾向
に絞って書いてください。

{log_text}
"""

    message = _client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_text(message)


def _extract_text(message) -> str:
    return "".join(block.text for block in message.content if block.type == "text").strip()
