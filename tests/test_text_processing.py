from videoflow.text_processing import clean_transcription_text, to_simplified_chinese


def test_traditional_chinese_is_converted_to_simplified() -> None:
    assert to_simplified_chinese("我們現在來講數值計算與方程組") == "我们现在来讲数值计算与方程组"


def test_excessive_character_and_phrase_repetition_is_collapsed() -> None:
    assert clean_transcription_text("小朋友们们们们们们们们") == "小朋友们们们"
    assert clean_transcription_text("我们来看看我们来看看我们来看看我们来看看") == "我们来看看我们来看看"


def test_normal_text_and_repeated_emphasis_are_preserved() -> None:
    assert clean_transcription_text("这个方程组需要使用高斯消元法。") == "这个方程组需要使用高斯消元法。"
    assert clean_transcription_text("哈哈哈") == "哈哈哈"
