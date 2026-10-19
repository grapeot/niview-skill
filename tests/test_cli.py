from niview_skill.cli import main


def test_help_exits_zero():
    assert main([]) == 0
