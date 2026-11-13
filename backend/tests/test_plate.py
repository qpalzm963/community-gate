from __future__ import annotations

from app.vision.plate import PlateVoter, VoteParams, clean, format_plate, normalize_ocr


def test_clean_and_format():
    assert clean("abc-1234 ") == "ABC1234"
    assert clean(" 123-abc") == "123ABC"
    assert format_plate("ABC1234") == "ABC-1234"
    assert format_plate("123ABC") == "123-ABC"
    assert format_plate("ABC123") == "ABC-123"


def test_normalize_tw_car_and_moto():
    # 汽車 3+4
    r = normalize_ocr("ABC-1234")
    assert r is not None and r.plate == "ABC1234" and r.corrections == 0
    # 易混淆字元校正：字母位 8→B，數字位 I→1（預設最多 2 個修正）
    r2 = normalize_ocr("A8C-I234")
    assert r2 is not None and r2.plate == "ABC1234" and r2.corrections == 2
    assert normalize_ocr("A8C-I2O4") is None
    r3 = normalize_ocr("A8C-I2O4", max_corrections=3)
    assert r3 is not None and r3.plate == "ABC1204" and r3.corrections == 3

    # 機車格式 3+3 與 3數字+3英文
    m1 = normalize_ocr("MKR-567")
    assert m1 is not None and m1.plate == "MKR567"
    m2 = normalize_ocr("123-XYZ")
    assert m2 is not None and m2.plate == "123XYZ"
    # 機車字元修正
    m3 = normalize_ocr("I23-XY2")
    assert m3 is not None and m3.plate == "123XYZ" and m3.corrections == 2

    # 超過修正上限或非車牌字串應排除
    assert normalize_ocr("HELLO") is None
    assert normalize_ocr("12", strict=True) is None
    assert normalize_ocr("AB1234", strict=False).plate == "AB1234"


def test_voter_threshold_and_dedup():
    v = PlateVoter(VoteParams(min_hits=3, window_sec=2.0, min_confidence=0.8, dedup_sec=30.0))
    assert v.add("ABC1234", 0.9, ts=10.0) is None
    assert v.add("ABC1234", 0.85, ts=10.4) is None
    c = v.add("ABC1234", 0.95, ts=10.8)
    assert c is not None
    assert c.plate == "ABC1234"
    assert c.hits == 3
    assert c.confidence == 0.9

    # 30 秒內去重（含編輯距離 <= 1 的近似誤讀），並延長去重時間
    assert v.add("ABC1234", 0.95, ts=15.0) is None
    assert v.add("ABC1235", 0.95, ts=20.0) is None

    # 超過 30 秒後可再次觸發
    assert v.add("ABC1234", 0.9, ts=55.0) is None
    assert v.add("ABC1234", 0.9, ts=55.3) is None
    c2 = v.add("ABC1234", 0.9, ts=55.6)
    assert c2 is not None and c2.plate == "ABC1234"


def test_voter_low_confidence_rejected():
    v = PlateVoter(VoteParams(min_hits=2, window_sec=2.0, min_confidence=0.85, dedup_sec=10.0))
    assert v.add("XYZ999", 0.7, ts=1.0) is None
    assert v.add("XYZ999", 0.8, ts=1.2) is None  # 平均 0.75 < 0.85
    c = v.add("XYZ999", 0.99, ts=1.4)  # 平均 (0.7+0.8+0.99)/3 = 0.83 < 0.85
    assert c is None
    assert v.add("XYZ999", 0.99, ts=1.6) is not None  # 平均 0.87 >= 0.85


def test_voter_merges_one_char_misreads():
    """同一車牌被交錯讀成相差一字（ABC1234 / ABC1Z34）時仍要在 min_hits 內確認，
    否則票數被拆散、車輛停在閘前等不到辨識；確認結果取多數讀法。"""
    v = PlateVoter(VoteParams(min_hits=3, window_sec=2.0, min_confidence=0.8, dedup_sec=30.0))
    assert v.add("ABC1234", 0.9, ts=1.0) is None
    assert v.add("ABC1Z34", 0.95, ts=1.2) is None
    c = v.add("ABC1234", 0.88, ts=1.4)
    assert c is not None
    assert c.plate == "ABC1234"
    assert c.hits == 3
    assert c.best.plate == "ABC1234" and c.best.confidence == 0.9
    # 誤讀版本已被併入，不會在去重期間被當成另一台車再確認
    assert v.add("ABC1Z34", 0.99, ts=1.6) is None
    assert v.add("ABC1Z34", 0.99, ts=1.8) is None


def test_voter_does_not_merge_distant_plates():
    v = PlateVoter(VoteParams(min_hits=3, window_sec=2.0, min_confidence=0.8, dedup_sec=30.0))
    assert v.add("ABC1234", 0.9, ts=1.0) is None
    assert v.add("XYZ5678", 0.9, ts=1.1) is None
    assert v.add("ABC1234", 0.9, ts=1.2) is None
    assert v.add("XYZ5678", 0.9, ts=1.3) is None
