def _append_xyz_valid(script_op, base_name, point, valid):
    vals = [0.0, 0.0, 0.0, float(valid)]
    if point:
        vals[0] = point[0]
        vals[1] = point[1]
        vals[2] = point[2] if len(point) > 2 else 0.0
    script_op.appendChan(base_name).vals = vals


def cook(scriptOp):
    scriptOp.clear()
    data = parent().fetch('hand_data', None)
    if data is None:
        return

    aruco = data.get('aruco', {})
    scriptOp.appendChan('box/aruco/ok').vals = [1 if aruco.get('ok', False) else 0]
    scriptOp.appendChan('box/aruco/stale').vals = [1 if aruco.get('stale', False) else 0]

    hands = data.get('hands', [])
    left_hand, right_hand = None, None
    for hand in hands:
        lm_box3 = hand.get('lm_box3')
        lm_img = hand.get('lm_img')
        if lm_box3:
            wrist_x = lm_box3[0][0]
        elif lm_img:
            wrist_x = lm_img[0][0]
        else:
            continue

        if wrist_x < 0.5:
            left_hand = hand
        else:
            right_hand = hand

    for side, hand in [('left', left_hand), ('right', right_hand)]:
        valid = 1 if (hand and hand.get('valid', False)) else 0
        lm_box3 = hand.get('lm_box3') if hand else None
        wrist = lm_box3[0] if lm_box3 and len(lm_box3) > 0 else None
        index_tip = lm_box3[8] if lm_box3 and len(lm_box3) > 8 else None

        _append_xyz_valid(scriptOp, f'box/hand/{side}/wrist', wrist, valid)
        _append_xyz_valid(scriptOp, f'box/hand/{side}/index_tip', index_tip, valid)

        # 旧アドレス互換が必要な場合だけ指先も出す
        _append_xyz_valid(scriptOp, f'box/finger/{side}', index_tip, valid)
