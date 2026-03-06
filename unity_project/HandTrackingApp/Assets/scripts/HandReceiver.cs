using UnityEngine;
using uOSC;

public class HandReceiver : MonoBehaviour
{
    [Header("左手の点（21個）")]
    public Transform[] leftPoints  = new Transform[21];

    [Header("右手の点（21個）")]
    public Transform[] rightPoints = new Transform[21];

    [Header("valid=0 のときにフェードするRenderer（左手）")]
    public Renderer[] leftRenderers;

    [Header("valid=0 のときにフェードするRenderer（右手）")]
    public Renderer[] rightRenderers;

    float _leftAlpha  = 0f;
    float _rightAlpha = 0f;
    bool  _leftValid  = false;
    bool  _rightValid = false;

    // TD は lm3d を63個の個別チャンネルで送る（1チャンネル=1値）
    // ここにバッファして Update() でまとめて適用する
    readonly float[] _leftLm  = new float[63];
    readonly float[] _rightLm = new float[63];
    bool _leftLmDirty  = false;
    bool _rightLmDirty = false;

    const string LeftLmPrefix  = "/box/hand/left/lm3d/";
    const string RightLmPrefix = "/box/hand/right/lm3d/";

    void Start()
    {
        var server = GetComponent<uOscServer>();
        server.onDataReceived.AddListener(OnDataReceived);
    }

    void OnDataReceived(Message message)
    {
        string addr = message.address;

        // --- lm3d: 個別チャンネル /box/hand/{side}/lm3d/{0..62} ---
        if (addr.StartsWith(LeftLmPrefix))
        {
            if (int.TryParse(addr.Substring(LeftLmPrefix.Length), out int idx)
                && idx >= 0 && idx < 63)
            {
                _leftLm[idx] = ToFloat(message.values[0]);
                _leftLmDirty = true;
            }
            return;
        }
        if (addr.StartsWith(RightLmPrefix))
        {
            if (int.TryParse(addr.Substring(RightLmPrefix.Length), out int idx)
                && idx >= 0 && idx < 63)
            {
                _rightLm[idx] = ToFloat(message.values[0]);
                _rightLmDirty = true;
            }
            return;
        }

        // --- valid / aruco など（1値チャンネル） ---
        switch (addr)
        {
            case "/box/hand/left/valid":
                _leftValid = ToFloat(message.values[0]) >= 0.5f;
                break;
            case "/box/hand/right/valid":
                _rightValid = ToFloat(message.values[0]) >= 0.5f;
                break;
        }
    }

    void ApplyBuffer(float[] lm, Transform[] points)
    {
        for (int i = 0; i < 21; i++)
        {
            float x = lm[i * 3];
            float y = lm[i * 3 + 1];
            float z = lm[i * 3 + 2];

            // x,y: 箱正面の正規化座標（左上=0,0 / 右下=1,1）
            // y は箱座標系で下が+ → Unity は上が+ なので反転
            points[i].localPosition = new Vector3(x, 1f - y, z * 0.1f);
        }
    }

    // TD は float で送るが uOSC が double に変換するケースがある
    static float ToFloat(object v) => v is float f ? f : (float)(double)v;

    void Update()
    {
        // バッファが更新されていたら点群に反映
        if (_leftLmDirty)
        {
            ApplyBuffer(_leftLm, leftPoints);
            _leftLmDirty = false;
        }
        if (_rightLmDirty)
        {
            ApplyBuffer(_rightLm, rightPoints);
            _rightLmDirty = false;
        }

        _leftAlpha  = Mathf.Lerp(_leftAlpha,  _leftValid  ? 1f : 0f, Time.deltaTime * 8f);
        _rightAlpha = Mathf.Lerp(_rightAlpha, _rightValid ? 1f : 0f, Time.deltaTime * 8f);
        SetAlpha(leftRenderers,  _leftAlpha);
        SetAlpha(rightRenderers, _rightAlpha);
    }

    void SetAlpha(Renderer[] renderers, float alpha)
    {
        foreach (var r in renderers)
        {
            // URP Lit の場合。Built-in の場合は "_Color" に変更
            var color = r.material.GetColor("_BaseColor");
            color.a = alpha;
            r.material.SetColor("_BaseColor", color);
        }
    }
}
