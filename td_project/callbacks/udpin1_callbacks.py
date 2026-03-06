import json

def onReceive(dat, rowIndex, message, bytes, peer):
    try:
        data = json.loads(message)
        parent().store('hand_data', data)
    except Exception as e:
        print('json parse error:', e)
    return
