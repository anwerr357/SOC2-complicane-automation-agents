from brain.llm import build_system_prompt

def test_build_system_prompt_is_public():
    result = build_system_prompt("Control text.", "CC6.7", "Encryption at rest")
    assert "CC6.7" in result
    assert "Encryption at rest" in result
    assert "SOC 2" in result
