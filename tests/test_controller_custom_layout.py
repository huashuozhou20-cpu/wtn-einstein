from einstein_wtn.game_controller import GameController


def test_new_game_custom_layouts_applied():
    red_layout = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (2, 0)}
    blue_layout = {1: (4, 4), 2: (4, 3), 3: (4, 2), 4: (3, 4), 5: (3, 3), 6: (2, 4)}
    ctrl = GameController(red_agent=None, blue_agent=None)
    ctrl.set_custom_layout(red_layout, blue_layout)
    ctrl.new_game_custom(red_layout, blue_layout, red_agent=None, blue_agent=None)

    assert ctrl.state.board[0][0] == 1
    assert ctrl.state.board[4][4] == -1
    assert ctrl.red_layout_coords[0] == (0, 0)
    assert ctrl.blue_layout_coords[5] == (2, 4)


def test_new_game_custom_allows_defaults():
    ctrl = GameController(red_agent=None, blue_agent=None)
    ctrl.new_game_custom(red_layout=None, blue_layout=None, red_agent=None, blue_agent=None)

    assert len(ctrl.state.pos_red) == 6
    assert len(ctrl.state.pos_blue) == 6
