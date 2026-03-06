def cook(scriptOp):
    scriptOp.clear()
    data = parent().fetch('hand_data', None)
    if data is None:
        return
    aruco = data.get('aruco', {})
    scriptOp.appendChan('box/aruco/ok').vals    = [1 if aruco.get('ok', False) else 0]
    scriptOp.appendChan('box/aruco/stale').vals = [1 if aruco.get('stale', False) else 0]
    hands = data.get('hands', [])
    left_hand, right_hand = None, None
    for h in hands:
        lm_box3 = h.get('lm_box3')
        lm_img  = h.get('lm_img')
        if lm_box3:
            wrist_x = lm_box3[0][0]
        elif lm_img:
            wrist_x = lm_img[0][0]
        else:
            continue
        if wrist_x < 0.5:
            left_hand = h
        else:
            right_hand = h
    for side, hand in [('left', left_hand), ('right', right_hand)]:
        valid = 1 if (hand and hand.get('valid', False)) else 0
        scriptOp.appendChan(f'box/hand/{side}/valid').vals = [valid]
        lm_vals = [0.0] * 63
        if hand and hand.get('lm_box3'):
            for i, pt in enumerate(hand['lm_box3'][:21]):
                lm_vals[i*3]     = pt[0]
                lm_vals[i*3+1]   = pt[1]
                lm_vals[i*3+2]   = pt[2] if len(pt) > 2 else 0.0
        # 63個の個別チャンネル（1サンプル）にする
        # OSC Out CHOP は1チャンネル=1メッセージなので
        # 1ch×63サンプルだと1値しか送れなかった
        for i in range(63):
            scriptOp.appendChan(f'box/hand/{side}/lm3d/{i}').vals = [lm_vals[i]]
